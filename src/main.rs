#![cfg_attr(not(debug_assertions), windows_subsystem = "windows")]

use std::path::PathBuf;

use pdf_layout_measure::PdfMeasure;

struct App {
    view: PdfMeasure,
    title: String,
}

impl eframe::App for App {
    fn update(&mut self, ctx: &egui::Context, _frame: &mut eframe::Frame) {
        // PDF trascinato sulla finestra
        if let Some(path) = ctx.input(|i| i.raw.dropped_files.iter().find_map(|f| f.path.clone())) {
            self.view.open(path);
        }
        egui::CentralPanel::default()
            .frame(egui::Frame::NONE)
            .show(ctx, |ui| self.view.show(ui));
        let version = pdf_layout_measure::VERSION;
        let title = match self.view.file_name() {
            Some(name) => format!("PDF Layout Measure {version} - {name}"),
            None => format!("PDF Layout Measure {version}"),
        };
        if title != self.title {
            ctx.send_viewport_cmd(egui::ViewportCommand::Title(title.clone()));
            self.title = title;
        }
    }
}

fn main() -> eframe::Result {
    let file_arg = std::env::args_os().nth(1).map(PathBuf::from);
    let mut viewport = egui::ViewportBuilder::default()
        .with_inner_size([1450.0, 900.0])
        .with_min_inner_size([1000.0, 650.0])
        .with_drag_and_drop(true);
    if let Ok(icon) = eframe::icon_data::from_png_bytes(include_bytes!("../assets/icona_256.png")) {
        viewport = viewport.with_icon(icon);
    }
    let options = eframe::NativeOptions {
        viewport,
        renderer: eframe::Renderer::Wgpu,
        ..Default::default()
    };
    eframe::run_native(
        "PDF Layout Measure",
        options,
        Box::new(move |cc| {
            let mut view = PdfMeasure::new(&cc.egui_ctx);
            if let Some(path) = file_arg {
                view.open(path);
            }
            Ok(Box::new(App { view, title: String::new() }))
        }),
    )
}
