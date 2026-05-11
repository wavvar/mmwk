pub mod commands;
pub mod contracts;
pub mod error;
pub mod protocol;
pub mod store;
pub mod transport;

use std::sync::Mutex;

pub struct AppState {
    pub db: Mutex<rusqlite::Connection>,
}

impl AppState {
    pub fn memory() -> rusqlite::Result<Self> {
        let conn = rusqlite::Connection::open_in_memory()?;
        store::schema::init(&conn)?;
        Ok(Self {
            db: Mutex::new(conn),
        })
    }
}

#[cfg(feature = "desktop")]
#[tauri::command]
fn app_health() -> &'static str {
    "ok"
}

#[cfg(feature = "desktop")]
pub fn run() {
    let state = AppState::memory().expect("failed to initialize MMWK GUI store");

    tauri::Builder::default()
        .manage(state)
        .invoke_handler(tauri::generate_handler![
            app_health,
            commands::profiles::list_device_profiles,
            commands::profiles::save_device_profile,
            commands::profiles::delete_device_profile,
            commands::profiles::list_server_profiles,
            commands::profiles::save_server_profile,
            commands::profiles::delete_server_profile,
            commands::device_control::execute_device_command
        ])
        .run(tauri::generate_context!())
        .expect("failed to run MMWK GUI");
}

#[cfg(not(feature = "desktop"))]
pub fn run() {
    panic!("build with --features desktop to run the Tauri shell");
}
