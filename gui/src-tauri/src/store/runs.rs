use rusqlite::{params, Connection, OptionalExtension, Result};
use serde::{Deserialize, Serialize};

#[derive(Debug, Clone, PartialEq, Eq, Serialize, Deserialize)]
pub struct ArtifactRun {
    pub id: String,
    pub label: String,
    pub status: String,
    pub started_at: i64,
    pub completed_at: Option<i64>,
}

pub fn create_run(conn: &Connection, run: &ArtifactRun) -> Result<()> {
    conn.execute(
        r#"
        INSERT INTO artifact_runs (id, label, status, started_at, completed_at)
        VALUES (?1, ?2, ?3, ?4, ?5)
        "#,
        params![
            run.id,
            run.label,
            run.status,
            run.started_at,
            run.completed_at
        ],
    )?;
    Ok(())
}

pub fn get_run(conn: &Connection, id: &str) -> Result<Option<ArtifactRun>> {
    conn.query_row(
        r#"
        SELECT id, label, status, started_at, completed_at
        FROM artifact_runs
        WHERE id = ?1
        "#,
        [id],
        |row| {
            Ok(ArtifactRun {
                id: row.get(0)?,
                label: row.get(1)?,
                status: row.get(2)?,
                started_at: row.get(3)?,
                completed_at: row.get(4)?,
            })
        },
    )
    .optional()
}
