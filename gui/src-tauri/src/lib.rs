pub mod contracts;

#[cfg(feature = "desktop")]
#[tauri::command]
fn app_health() -> &'static str {
    "ok"
}

#[cfg(feature = "desktop")]
pub fn run() {
    tauri::Builder::default()
        .invoke_handler(tauri::generate_handler![app_health])
        .run(tauri::generate_context!())
        .expect("failed to run MMWK GUI");
}

#[cfg(not(feature = "desktop"))]
pub fn run() {
    panic!("build with --features desktop to run the Tauri shell");
}
