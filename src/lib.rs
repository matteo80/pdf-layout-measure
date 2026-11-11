//! PDF Layout Measure: lettura di misure da layout in PDF.
//!
//! Il widget [`PdfMeasure`] si usa da solo (vedi `main.rs`) o dentro un'altra app egui
//! (es. Dima 3D): `PdfMeasure::new(ctx)` una volta, poi `show(ui)` a ogni frame.

pub mod measure;
pub mod render;
pub mod tiles;
mod viewer;

pub use viewer::{default_library_dirs, PdfMeasure, Tool};

pub const VERSION: &str = concat!("V", env!("CARGO_PKG_VERSION"));
