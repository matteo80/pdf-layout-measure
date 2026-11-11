//! Il widget completo senza finestra: contesto egui vero, thread pdfium vero, clic simulati.

use std::path::{Path, PathBuf};
use std::time::Duration;

use egui::{pos2, Event, Key, Modifiers, PointerButton, Pos2, RawInput, Rect};
use pdf_layout_measure::PdfMeasure;

/// PDF minimale scritto a mano: una pagina 600×400 pt con un rettangolo grigio.
fn write_pdf(path: &Path) {
    let content = "0.5 g 100 100 400 200 re f";
    let objects = [
        "<< /Type /Catalog /Pages 2 0 R >>".to_string(),
        "<< /Type /Pages /Kids [3 0 R] /Count 1 >>".to_string(),
        "<< /Type /Page /Parent 2 0 R /MediaBox [0 0 600 400] /Contents 4 0 R >>".to_string(),
        format!("<< /Length {} >>\nstream\n{content}\nendstream", content.len()),
    ];
    let mut pdf = String::from("%PDF-1.4\n");
    let mut offsets = Vec::new();
    for (i, o) in objects.iter().enumerate() {
        offsets.push(pdf.len());
        pdf += &format!("{} 0 obj\n{o}\nendobj\n", i + 1);
    }
    let xref = pdf.len();
    pdf += &format!("xref\n0 {}\n0000000000 65535 f \n", objects.len() + 1);
    for o in offsets {
        pdf += &format!("{o:010} 00000 n \n");
    }
    pdf += &format!("trailer\n<< /Size {} /Root 1 0 R >>\nstartxref\n{xref}\n%%EOF\n", objects.len() + 1);
    std::fs::write(path, pdf).unwrap();
}

struct Harness {
    ctx: egui::Context,
    view: PdfMeasure,
}

impl Harness {
    fn frame(&mut self, events: Vec<Event>) {
        let input = RawInput {
            screen_rect: Some(Rect::from_min_size(Pos2::ZERO, egui::vec2(1400.0, 900.0))),
            events,
            ..Default::default()
        };
        let view = &mut self.view;
        let _ = self.ctx.run(input, |ctx| {
            egui::CentralPanel::default().frame(egui::Frame::NONE).show(ctx, |ui| view.show(ui));
        });
    }

    fn click(&mut self, p: Pos2) {
        self.frame(vec![Event::PointerMoved(p)]);
        let button = |pressed| Event::PointerButton { pos: p, button: PointerButton::Primary, pressed, modifiers: Modifiers::NONE };
        self.frame(vec![button(true)]);
        self.frame(vec![button(false)]);
    }

    fn wait(&mut self, mut done: impl FnMut(&PdfMeasure) -> bool) {
        for _ in 0..300 {
            self.frame(vec![]);
            if done(&self.view) {
                return;
            }
            std::thread::sleep(Duration::from_millis(10));
        }
        panic!("timeout");
    }
}

#[test]
fn open_render_calibrate_and_measure() {
    let dir = std::env::temp_dir().join(format!("pdfm-test-{}", std::process::id()));
    std::fs::create_dir_all(&dir).unwrap();
    let pdf = dir.join("layout.pdf");
    write_pdf(&pdf);

    let ctx = egui::Context::default();
    let lib = PathBuf::from(env!("CARGO_MANIFEST_DIR")).join("third_party/pdfium/bin");
    let mut h = Harness { view: PdfMeasure::with_library_dirs(&ctx, vec![lib]), ctx };
    h.frame(vec![]);
    h.view.open(&pdf);
    h.wait(|v| v.page_count() == 1);
    // Tutte le tile visibili e la corona arrivano dal thread di rendering.
    h.wait(|v| {
        let (tiles, queued) = v.tile_stats();
        tiles > 0 && queued == 0
    });

    // Calibrazione: 200 punti in orizzontale = 1000 mm.
    let c = pos2(550.0, 480.0);
    h.view.start_calibration();
    h.click(c + egui::vec2(-100.0, 0.0));
    h.click(c + egui::vec2(100.0, 0.0));
    h.frame(vec![]);
    h.frame(vec![Event::Text("1000".into())]);
    h.frame(vec![Event::Key { key: Key::Enter, physical_key: None, pressed: true, repeat: false, modifiers: Modifiers::NONE }]);
    h.frame(vec![]);
    let cal = h.view.calibration().expect("scala calibrata").clone();

    // Misura: 60 punti in X e 80 in Y → 100 punti = 500 mm.
    h.view.start_measurement();
    h.click(c + egui::vec2(-30.0, -40.0));
    h.click(c + egui::vec2(30.0, 40.0));
    let m = h.view.measurement().expect("misura").clone();
    assert!((m.dx_mm - 300.0).abs() < 0.01, "{m:?} {cal:?}");
    assert!((m.dy_mm - 400.0).abs() < 0.01, "{m:?}");
    assert!((m.d_mm - 500.0).abs() < 0.01, "{m:?}");

    std::fs::remove_dir_all(&dir).ok();
}
