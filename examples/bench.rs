//! Tempi di rendering delle tile.
//!
//!   cargo run --release --example bench -- [file.pdf]
//!
//! Se il file non esiste (o senza argomenti: `bench_layout.pdf` nella cartella temporanea) genera
//! un A0 orizzontale con decine di migliaia di linee, simile a un layout CAD.

use std::path::PathBuf;
use std::time::Instant;

use pdf_layout_measure::render::{bind_pdfium, render_region};
use pdf_layout_measure::tiles::{page_px, tile_px_rect, TILE_PX};
use pdfium_render::prelude::*;

fn main() {
    let dir = PathBuf::from(env!("CARGO_MANIFEST_DIR")).join("third_party/pdfium/bin");
    let pdfium = Pdfium::new(bind_pdfium(&[dir]).expect("pdfium"));
    // Se il file indicato non esiste viene generato lì.
    let path = std::env::args_os()
        .nth(1)
        .map(PathBuf::from)
        .unwrap_or_else(|| std::env::temp_dir().join("bench_layout.pdf"));
    if !path.exists() {
        generate(&path);
    }
    println!("file: {}", path.display());

    let t = Instant::now();
    let doc = pdfium.load_pdf_from_file(&path, None).unwrap();
    let page = doc.pages().get(0).unwrap();
    let size = [page.width().value, page.height().value];
    println!("apertura + caricamento pagina: {:.0} ms ({} x {} pt)", ms(t), size[0], size[1]);

    let t = Instant::now();
    let scale = 2048.0 / size[0].max(size[1]);
    let px = page_px(size, scale);
    render_region(&page, scale, 0, 0, px[0], px[1]).unwrap();
    println!("anteprima {}x{}: {:.0} ms", px[0], px[1], ms(t));

    for zoom in [1.5f32, 4.0, 8.0] {
        let px = page_px(size, zoom);
        // Una vista 1920x1080 al centro della pagina, più la corona di precaricamento.
        let cx = px[0] / 2 / TILE_PX;
        let cy = px[1] / 2 / TILE_PX;
        let tiles: Vec<(u32, u32)> = (cy.saturating_sub(2)..=cy + 2)
            .flat_map(|r| (cx.saturating_sub(3)..=cx + 3).map(move |c| (c, r)))
            .filter(|&(c, r)| c * TILE_PX < px[0] && r * TILE_PX < px[1])
            .collect();
        let t = Instant::now();
        for &(c, r) in &tiles {
            let [x, y, w, h] = tile_px_rect(c, r, px);
            render_region(&page, zoom, x, y, w, h).unwrap();
        }
        let cached = ms(t);
        // Come lo script Python: la pagina viene ricaricata per ogni tile.
        let t = Instant::now();
        for &(c, r) in &tiles {
            let p = doc.pages().get(0).unwrap();
            let [x, y, w, h] = tile_px_rect(c, r, px);
            render_region(&p, zoom, x, y, w, h).unwrap();
        }
        let reloaded = ms(t);
        println!(
            "zoom {:>4}%: {} tile in {:.0} ms ({:.1} ms/tile) · ricaricando la pagina: {:.0} ms ({:.1} ms/tile)",
            zoom * 100.0,
            tiles.len(),
            cached,
            cached / tiles.len() as f64,
            reloaded,
            reloaded / tiles.len() as f64
        );
    }
}

fn ms(t: Instant) -> f64 {
    t.elapsed().as_secs_f64() * 1000.0
}

/// Scrive il PDF a mano (un solo flusso di contenuto, come un layout esportato da CAD):
/// aggiungere 40.000 oggetti uno per uno con pdfium-render richiederebbe quasi un'ora.
fn generate(path: &std::path::Path) {
    use std::fmt::Write as _;
    let t = Instant::now();
    let (w, h) = (3370.0f32, 2384.0f32); // A0 orizzontale
    let mut seed = 12345u32;
    let mut rnd = || {
        seed ^= seed << 13;
        seed ^= seed >> 17;
        seed ^= seed << 5;
        seed as f32 / u32::MAX as f32
    };
    let n = 40_000;
    let mut content = String::new();
    for _ in 0..n {
        let x = rnd() * w;
        let y = rnd() * h;
        let (dx, dy) = if rnd() < 0.5 { (rnd() * 120.0, 0.0) } else { (0.0, rnd() * 120.0) };
        let (r, g, b) = (rnd() * 0.8, rnd() * 0.8, rnd() * 0.8);
        let lw = 0.3 + rnd();
        writeln!(content, "{r:.3} {g:.3} {b:.3} RG {lw:.2} w {x:.2} {y:.2} m {:.2} {:.2} l S", (x + dx).min(w), (y + dy).min(h)).unwrap();
    }
    for i in 0..3000 {
        let x = rnd() * (w - 40.0);
        let y = rnd() * (h - 40.0);
        let (rw, rh) = (5.0 + rnd() * 30.0, 5.0 + rnd() * 30.0);
        let op = if i % 3 == 0 { "B" } else { "S" };
        writeln!(content, "0.08 G 0.47 0.63 0.86 rg 0.5 w {x:.2} {y:.2} {rw:.2} {rh:.2} re {op}").unwrap();
    }
    let objects = [
        "<< /Type /Catalog /Pages 2 0 R >>".to_string(),
        "<< /Type /Pages /Kids [3 0 R] /Count 1 >>".to_string(),
        format!("<< /Type /Page /Parent 2 0 R /MediaBox [0 0 {w} {h}] /Contents 4 0 R >>"),
        format!("<< /Length {} >>
stream
{content}endstream", content.len()),
    ];
    let mut pdf = String::from("%PDF-1.4
");
    let mut offsets = Vec::new();
    for (i, o) in objects.iter().enumerate() {
        offsets.push(pdf.len());
        write!(pdf, "{} 0 obj
{o}
endobj
", i + 1).unwrap();
    }
    let xref = pdf.len();
    write!(pdf, "xref
0 {}
0000000000 65535 f 
", objects.len() + 1).unwrap();
    for o in offsets {
        write!(pdf, "{o:010} 00000 n 
").unwrap();
    }
    write!(pdf, "trailer
<< /Size {} /Root 1 0 R >>
startxref
{xref}
%%EOF
", objects.len() + 1).unwrap();
    std::fs::write(path, pdf).unwrap();
    println!("generato {} ({n} linee + 3000 rettangoli) in {:.0} ms", path.display(), ms(t));
}
