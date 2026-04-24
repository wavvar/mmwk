#!/usr/bin/env bash

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
VENV_DIR="${SCRIPT_DIR}/.venv"
PYTHON_BIN="${VENV_DIR}/bin/python"
PIP_BIN="${VENV_DIR}/bin/pip"

usage() {
  echo "Usage: $0 pdfs --version <vX.Y.Z> --built-date <YYYY-MM-DD> --out-dir <dir>" >&2
}

require_command() {
  local name="$1"
  if ! command -v "${name}" >/dev/null 2>&1; then
    echo "${name} is required" >&2
    exit 1
  fi
}

subcommand="${1:-}"
if [[ $# -gt 0 ]]; then
  shift
fi

version=""
built_date=""
out_dir=""

while [[ $# -gt 0 ]]; do
  case "$1" in
    --version|--built-date|--out-dir)
      if [[ $# -lt 2 ]]; then
        echo "Missing value for $1" >&2
        usage
        exit 1
      fi
      case "$1" in
        --version) version="$2" ;;
        --built-date) built_date="$2" ;;
        --out-dir) out_dir="$2" ;;
      esac
      shift 2
      ;;
    *)
      echo "Unknown argument: $1" >&2
      usage
      exit 1
      ;;
  esac
done

if [[ "${subcommand}" != "pdfs" ]]; then
  echo "Unknown subcommand: ${subcommand:-<empty>}" >&2
  usage
  exit 1
fi

if [[ -z "${version}" || -z "${built_date}" || -z "${out_dir}" ]]; then
  usage
  exit 1
fi

if [[ "${version}" != v* ]]; then
  echo "--version must start with v" >&2
  exit 1
fi

if [[ ! "${built_date}" =~ ^[0-9]{4}-[0-9]{2}-[0-9]{2}$ ]]; then
  echo "--built-date must be in YYYY-MM-DD format" >&2
  exit 1
fi

require_command python3
require_command pandoc

if [[ ! -d "${VENV_DIR}" ]]; then
  python3 -m venv "${VENV_DIR}"
fi

"${PIP_BIN}" install reportlab pypdf

display_version="${version#v}"
mkdir -p "${out_dir}"

"${PYTHON_BIN}" "${SCRIPT_DIR}/generate_module_pdfs.py" \
  --display-version "${display_version}" \
  --built-date "${built_date}" \
  --out-dir "${out_dir}"
