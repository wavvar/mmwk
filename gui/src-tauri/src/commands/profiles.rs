use rusqlite::Connection;

use crate::{
    error::CommandEnvelope,
    store::{
        device_profiles::{
            delete_device_profile, list_device_profiles, save_device_profile, DeviceProfile,
        },
        server_profiles::{
            delete_server_profile, list_server_profiles, save_server_profile, ServerProfile,
        },
    },
};

pub fn list_device_profiles_command(
    conn: &Connection,
) -> CommandEnvelope<Vec<DeviceProfile>> {
    from_store_result(list_device_profiles(conn))
}

pub fn save_device_profile_command(
    conn: &Connection,
    profile: DeviceProfile,
) -> CommandEnvelope<DeviceProfile> {
    if profile.id.trim().is_empty() {
        return CommandEnvelope::error("validation", "device profile id is required");
    }
    if profile.name.trim().is_empty() {
        return CommandEnvelope::error("validation", "device profile name is required");
    }
    if profile.profile.trim().is_empty() {
        return CommandEnvelope::error("validation", "device profile kind is required");
    }
    if profile.transport.trim().is_empty() {
        return CommandEnvelope::error("validation", "device transport is required");
    }

    match save_device_profile(conn, &profile) {
        Ok(()) => CommandEnvelope::success(profile),
        Err(err) => CommandEnvelope::error("store", err.to_string()),
    }
}

pub fn delete_device_profile_command(
    conn: &Connection,
    id: String,
) -> CommandEnvelope<()> {
    if id.trim().is_empty() {
        return CommandEnvelope::error("validation", "device profile id is required");
    }
    from_store_result(delete_device_profile(conn, &id))
}

pub fn list_server_profiles_command(
    conn: &Connection,
) -> CommandEnvelope<Vec<ServerProfile>> {
    from_store_result(list_server_profiles(conn))
}

pub fn save_server_profile_command(
    conn: &Connection,
    profile: ServerProfile,
) -> CommandEnvelope<ServerProfile> {
    if profile.id.trim().is_empty() {
        return CommandEnvelope::error("validation", "server profile id is required");
    }
    if profile.name.trim().is_empty() {
        return CommandEnvelope::error("validation", "server profile name is required");
    }

    match save_server_profile(conn, &profile) {
        Ok(()) => CommandEnvelope::success(profile),
        Err(err) => CommandEnvelope::error("store", err.to_string()),
    }
}

pub fn delete_server_profile_command(
    conn: &Connection,
    id: String,
) -> CommandEnvelope<()> {
    if id.trim().is_empty() {
        return CommandEnvelope::error("validation", "server profile id is required");
    }
    from_store_result(delete_server_profile(conn, &id))
}

fn from_store_result<T>(result: rusqlite::Result<T>) -> CommandEnvelope<T> {
    match result {
        Ok(data) => CommandEnvelope::success(data),
        Err(err) => CommandEnvelope::error("store", err.to_string()),
    }
}

#[cfg(feature = "desktop")]
mod tauri_commands {
    use tauri::State;

    use super::*;
    use crate::AppState;

    #[tauri::command]
    pub fn list_device_profiles(
        state: State<'_, AppState>,
    ) -> CommandEnvelope<Vec<DeviceProfile>> {
        with_conn(&state, list_device_profiles_command)
    }

    #[tauri::command]
    pub fn save_device_profile(
        state: State<'_, AppState>,
        profile: DeviceProfile,
    ) -> CommandEnvelope<DeviceProfile> {
        with_conn(&state, |conn| save_device_profile_command(conn, profile))
    }

    #[tauri::command]
    pub fn delete_device_profile(
        state: State<'_, AppState>,
        id: String,
    ) -> CommandEnvelope<()> {
        with_conn(&state, |conn| delete_device_profile_command(conn, id))
    }

    #[tauri::command]
    pub fn list_server_profiles(
        state: State<'_, AppState>,
    ) -> CommandEnvelope<Vec<ServerProfile>> {
        with_conn(&state, list_server_profiles_command)
    }

    #[tauri::command]
    pub fn save_server_profile(
        state: State<'_, AppState>,
        profile: ServerProfile,
    ) -> CommandEnvelope<ServerProfile> {
        with_conn(&state, |conn| save_server_profile_command(conn, profile))
    }

    #[tauri::command]
    pub fn delete_server_profile(
        state: State<'_, AppState>,
        id: String,
    ) -> CommandEnvelope<()> {
        with_conn(&state, |conn| delete_server_profile_command(conn, id))
    }

    fn with_conn<T>(
        state: &State<'_, AppState>,
        f: impl FnOnce(&Connection) -> CommandEnvelope<T>,
    ) -> CommandEnvelope<T> {
        match state.db.lock() {
            Ok(conn) => f(&conn),
            Err(err) => CommandEnvelope::error("store_lock", err.to_string()),
        }
    }
}

#[cfg(feature = "desktop")]
pub use tauri_commands::*;
