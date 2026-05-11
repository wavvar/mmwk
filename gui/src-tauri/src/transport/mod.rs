pub mod mqtt;
pub mod serial;

use std::{
    sync::{
        atomic::{AtomicBool, Ordering},
        Arc,
    },
    time::Duration,
};

use thiserror::Error;

use crate::protocol::{
    cliv1::Cliv1Request,
    envelope::{Cliv1Frame, Cliv1Response},
};

#[derive(Debug, Error, PartialEq, Eq)]
pub enum TransportError {
    #[error("transport timed out")]
    Timeout,
    #[error("transport operation cancelled")]
    Cancelled,
    #[error("transport protocol error: {0}")]
    Protocol(String),
    #[error("transport I/O error: {0}")]
    Io(String),
}

#[derive(Debug, Clone, Default)]
pub struct CancellationFlag {
    cancelled: Arc<AtomicBool>,
}

impl CancellationFlag {
    pub fn cancel(&self) {
        self.cancelled.store(true, Ordering::SeqCst);
    }

    pub fn is_cancelled(&self) -> bool {
        self.cancelled.load(Ordering::SeqCst)
    }
}

pub trait DeviceTransport {
    fn exchange(
        &mut self,
        request: &Cliv1Request,
        timeout: Duration,
    ) -> Result<Cliv1Frame, TransportError>;
}

pub fn request_with_retries<T: DeviceTransport>(
    transport: &mut T,
    request: &Cliv1Request,
    retries: usize,
    timeout: Duration,
    cancellation: &CancellationFlag,
) -> Result<Cliv1Response, TransportError> {
    let attempts = retries.max(1);
    let mut last_error = TransportError::Timeout;

    for _ in 0..attempts {
        if cancellation.is_cancelled() {
            return Err(TransportError::Cancelled);
        }

        match transport.exchange(request, timeout) {
            Ok(Cliv1Frame::Response(response)) if response.seq == request.seq => {
                return Ok(response);
            }
            Ok(Cliv1Frame::Response(response)) => {
                last_error = TransportError::Protocol(format!(
                    "response seq {} did not match request seq {}",
                    response.seq, request.seq
                ));
            }
            Ok(Cliv1Frame::Event(event)) => {
                last_error = TransportError::Protocol(format!(
                    "received event {}.{} while waiting for response",
                    event.service, event.event
                ));
            }
            Ok(Cliv1Frame::Text(text)) => {
                last_error = TransportError::Protocol(format!(
                    "received text while waiting for response: {text}"
                ));
            }
            Err(err) => {
                last_error = err;
            }
        }
    }

    Err(last_error)
}

#[cfg(test)]
mod tests;
