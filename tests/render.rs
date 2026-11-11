//! Rendering reale con pdfium: servono i binari in `third_party/pdfium/bin`.

use std::path::PathBuf;

use pdf_layout_measure::render::{bind_pdfium, render_region};
use pdf_layout_measure::tiles::{page_px, tile_px_rect, TILE_PX};
use pdfium_render::prelude::*;

fn pdfium() -> Pdfium {
    let dir = PathBuf::from(env!("CARGO_MANIFEST_DIR")).join("third_party/pdfium/bin");
    Pdfium::new(bind_pdfium(&[dir]).expect("pdfium.dll in third_party/pdfium/bin"))
}

/// Pagina 600×400 pt con un rettangolo nero in (100..200, 100..150) in coordinate PDF
/// (origine in basso a sinistra) e qualche linea per avere contenuto su tutte le tile.
fn sample_pdf(pdfium: &Pdfium, rotate: Option<PdfPageRenderRotation>, lines: bool) -> Vec<u8> {
    let mut doc = pdfium.create_new_pdf().unwrap();
    let mut page = doc
        .pages_mut()
        .create_page_at_end(PdfPagePaperSize::from_points(PdfPoints::new(600.0), PdfPoints::new(400.0)))
        .unwrap();
    page.objects_mut()
        .create_path_object_rect(
            PdfRect::new_from_values(100.0, 100.0, 150.0, 200.0),
            None,
            None,
            Some(PdfColor::new(0, 0, 0, 255)),
        )
        .unwrap();
    for i in 0..if lines { 40 } else { 0 } {
        let x = 10.0 + i as f32 * 14.5;
        page.objects_mut()
            .create_path_object_line(
                PdfPoints::new(x),
                PdfPoints::new(5.0),
                PdfPoints::new(595.0 - x),
                PdfPoints::new(395.0),
                PdfColor::new(200, 30, 30, 255),
                PdfPoints::new(0.8),
            )
            .unwrap();
    }
    if let Some(r) = rotate {
        page.set_rotation(r);
    }
    doc.save_to_bytes().unwrap()
}

fn pixel(img: &egui::ColorImage, x: usize, y: usize) -> egui::Color32 {
    img.pixels[y * img.size[0] + x]
}

#[test]
fn coordinates_are_top_left_and_scaled() {
    let pdfium = pdfium();
    let bytes = sample_pdf(&pdfium, None, false);
    let doc = pdfium.load_pdf_from_byte_slice(&bytes, None).unwrap();
    let page = doc.pages().get(0).unwrap();
    assert_eq!((page.width().value, page.height().value), (600.0, 400.0));

    // Scala 2: il rettangolo nero va da x 200..400, y (400-150)*2=500 .. (400-100)*2=600.
    let img = render_region(&page, 2.0, 0, 0, 1200, 800).unwrap();
    assert_eq!(img.size, [1200, 800]);
    assert_eq!(pixel(&img, 300, 550), egui::Color32::BLACK);
    assert_eq!(pixel(&img, 190, 550), egui::Color32::WHITE);
    assert_eq!(pixel(&img, 300, 490), egui::Color32::WHITE);
    assert_eq!(pixel(&img, 300, 610), egui::Color32::WHITE);
}

#[test]
fn stitched_tiles_match_full_render() {
    let pdfium = pdfium();
    let bytes = sample_pdf(&pdfium, None, true);
    let doc = pdfium.load_pdf_from_byte_slice(&bytes, None).unwrap();
    let page = doc.pages().get(0).unwrap();
    let scale = 2.37;
    let px = page_px([600.0, 400.0], scale);
    let full = render_region(&page, scale, 0, 0, px[0], px[1]).unwrap();
    let cols = px[0].div_ceil(TILE_PX);
    let rows = px[1].div_ceil(TILE_PX);
    let mut differing = 0usize;
    for row in 0..rows {
        for col in 0..cols {
            let [x, y, w, h] = tile_px_rect(col, row, px);
            let tile = render_region(&page, scale, x, y, w, h).unwrap();
            assert_eq!(tile.size, [w as usize, h as usize]);
            for ty in 0..h as usize {
                for tx in 0..w as usize {
                    let a = pixel(&tile, tx, ty);
                    let b = pixel(&full, x as usize + tx, y as usize + ty);
                    let d = a.r().abs_diff(b.r()).max(a.g().abs_diff(b.g())).max(a.b().abs_diff(b.b()));
                    if d > 8 {
                        differing += 1;
                    }
                }
            }
        }
    }
    // L'antialiasing ai bordi delle tile può variare di poco su pochissimi pixel.
    let total = (px[0] * px[1]) as usize;
    assert!(differing * 1000 < total, "{differing} pixel diversi su {total}");
}

#[test]
fn rotated_page_reports_rotated_size() {
    let pdfium = pdfium();
    let bytes = sample_pdf(&pdfium, Some(PdfPageRenderRotation::Degrees90), false);
    let doc = pdfium.load_pdf_from_byte_slice(&bytes, None).unwrap();
    let page = doc.pages().get(0).unwrap();
    assert_eq!((page.width().value, page.height().value), (400.0, 600.0));
    let img = render_region(&page, 1.0, 0, 0, 400, 600).unwrap();
    // Ruotata di 90° in senso orario (x' = 400 - y, y' = x) il rettangolo sta in x 100..150, y 100..200.
    assert_eq!(pixel(&img, 125, 150), egui::Color32::BLACK);
    assert_eq!(pixel(&img, 275, 150), egui::Color32::WHITE);
    let size = doc.pages().page_size(0).unwrap();
    eprintln!("page_size senza caricare la pagina: {} x {}", size.width().value, size.height().value);
}
