use std::{
    fs,
    path::{Path, PathBuf},
    sync::{
        atomic::{AtomicU64, Ordering},
        Arc,
    },
};

use axum::{
    body::Bytes,
    extract::{Path as AxumPath, State},
    http::StatusCode,
    response::{IntoResponse, Response},
    routing::{get, post},
    Router,
};
use serde::{Deserialize, Serialize};

#[derive(Debug, Clone, PartialEq, Eq, Serialize, Deserialize)]
pub struct HttpServerConfig {
    pub host: String,
    pub port: u16,
    pub serve_dir: PathBuf,
    pub upload_dir: PathBuf,
}

#[derive(Debug, Clone, PartialEq, Eq, Serialize, Deserialize)]
pub struct HttpServerStatus {
    pub running: bool,
    pub base_url: String,
    pub served_requests: u64,
    pub uploads_received: u64,
}

#[derive(Debug, Default)]
struct HttpCounters {
    served_requests: AtomicU64,
    uploads_received: AtomicU64,
}

#[derive(Debug, Clone)]
struct HttpState {
    config: HttpServerConfig,
    counters: Arc<HttpCounters>,
}

pub fn router(config: HttpServerConfig) -> Router {
    let state = HttpState {
        config,
        counters: Arc::new(HttpCounters::default()),
    };

    Router::new()
        .route("/status", get(status))
        .route("/files/{*path}", get(download_file))
        .route("/upload/{name}", post(upload_file))
        .with_state(state)
}

pub fn status_from_config(config: &HttpServerConfig, running: bool) -> HttpServerStatus {
    HttpServerStatus {
        running,
        base_url: format!("http://{}:{}", config.host, config.port),
        served_requests: 0,
        uploads_received: 0,
    }
}

async fn status(State(state): State<HttpState>) -> impl IntoResponse {
    axum::Json(HttpServerStatus {
        running: true,
        base_url: format!("http://{}:{}", state.config.host, state.config.port),
        served_requests: state.counters.served_requests.load(Ordering::SeqCst),
        uploads_received: state.counters.uploads_received.load(Ordering::SeqCst),
    })
}

async fn download_file(
    State(state): State<HttpState>,
    AxumPath(path): AxumPath<String>,
) -> Response {
    state.counters.served_requests.fetch_add(1, Ordering::SeqCst);

    let path = match safe_join(&state.config.serve_dir, &path) {
        Some(path) => path,
        None => return StatusCode::BAD_REQUEST.into_response(),
    };
    match fs::read(path) {
        Ok(body) => body.into_response(),
        Err(err) if err.kind() == std::io::ErrorKind::NotFound => {
            StatusCode::NOT_FOUND.into_response()
        }
        Err(_) => StatusCode::INTERNAL_SERVER_ERROR.into_response(),
    }
}

async fn upload_file(
    State(state): State<HttpState>,
    AxumPath(name): AxumPath<String>,
    body: Bytes,
) -> Response {
    let path = match safe_join(&state.config.upload_dir, &name) {
        Some(path) => path,
        None => return StatusCode::BAD_REQUEST.into_response(),
    };
    if let Some(parent) = path.parent() {
        if fs::create_dir_all(parent).is_err() {
            return StatusCode::INTERNAL_SERVER_ERROR.into_response();
        }
    }

    match fs::write(path, body) {
        Ok(()) => {
            state.counters.uploads_received.fetch_add(1, Ordering::SeqCst);
            StatusCode::CREATED.into_response()
        }
        Err(_) => StatusCode::INTERNAL_SERVER_ERROR.into_response(),
    }
}

fn safe_join(root: &Path, relative: &str) -> Option<PathBuf> {
    let relative = Path::new(relative);
    if relative.is_absolute()
        || relative
            .components()
            .any(|component| matches!(component, std::path::Component::ParentDir))
    {
        return None;
    }
    Some(root.join(relative))
}

#[cfg(test)]
mod tests {
    use super::*;
    use axum::body::Body;
    use http::{Method, Request, StatusCode};
    use tower::ServiceExt;

    fn temp_dir(name: &str) -> PathBuf {
        let path = std::env::temp_dir().join(format!(
            "mmwk-gui-http-{}-{}",
            std::process::id(),
            name
        ));
        let _ = fs::remove_dir_all(&path);
        fs::create_dir_all(&path).unwrap();
        path
    }

    #[tokio::test]
    async fn serves_files_and_reports_status() {
        let serve_dir = temp_dir("serve");
        let upload_dir = temp_dir("upload");
        fs::write(serve_dir.join("firmware.bin"), b"firmware").unwrap();
        let app = router(HttpServerConfig {
            host: "127.0.0.1".to_string(),
            port: 0,
            serve_dir,
            upload_dir,
        });

        let response = app
            .clone()
            .oneshot(
                Request::builder()
                    .method(Method::GET)
                    .uri("/files/firmware.bin")
                    .body(Body::empty())
                    .unwrap(),
            )
            .await
            .unwrap();
        assert_eq!(response.status(), StatusCode::OK);

        let status = app
            .oneshot(
                Request::builder()
                    .method(Method::GET)
                    .uri("/status")
                    .body(Body::empty())
                    .unwrap(),
            )
            .await
            .unwrap();
        assert_eq!(status.status(), StatusCode::OK);
    }

    #[tokio::test]
    async fn receives_uploads_and_rejects_path_traversal() {
        let serve_dir = temp_dir("serve-upload");
        let upload_dir = temp_dir("upload-target");
        let app = router(HttpServerConfig {
            host: "127.0.0.1".to_string(),
            port: 0,
            serve_dir,
            upload_dir: upload_dir.clone(),
        });

        let response = app
            .clone()
            .oneshot(
                Request::builder()
                    .method(Method::POST)
                    .uri("/upload/capture.sraw")
                    .body(Body::from("raw"))
                    .unwrap(),
            )
            .await
            .unwrap();
        assert_eq!(response.status(), StatusCode::CREATED);
        assert_eq!(fs::read(upload_dir.join("capture.sraw")).unwrap(), b"raw");

        let response = app
            .oneshot(
                Request::builder()
                    .method(Method::GET)
                    .uri("/files/../secret")
                    .body(Body::empty())
                    .unwrap(),
            )
            .await
            .unwrap();
        assert_eq!(response.status(), StatusCode::BAD_REQUEST);
    }
}
