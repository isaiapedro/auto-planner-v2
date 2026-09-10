"""Read the declarative Personal Account destination catalog safely.

The catalog is a resolver, not an access-control bypass. It returns only
Registry-approved relative paths and proposal capabilities; it has no generic
filesystem read or write operation.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping

import yaml

from config import settings
from schemas import AccountCatalogResponse, AccountDestination, CatalogContextResource


class AccountCatalogError(RuntimeError):
    """The account-routing contract is unavailable or internally inconsistent."""


@dataclass(frozen=True)
class CatalogValidationResult:
    """A complete, non-sensitive authorization result for one contract revision.

    Callers must obtain this object before routing or resolving a proposal. It
    proves that the root configuration, repository ownership, destination
    manifest and allow-listed context resources all validated together.
    """

    catalog: AccountCatalogResponse
    catalog_fingerprint: str
    destinations_by_id: Mapping[str, AccountDestination]

    def require_destination(self, destination_id: str) -> AccountDestination:
        destination = self.destinations_by_id.get(destination_id)
        if destination is None:
            raise AccountCatalogError("Account proposal target is not authorized")
        return destination


def _load_yaml(path: Path) -> dict[str, Any]:
    try:
        with path.open("r", encoding="utf-8") as source:
            value = yaml.safe_load(source)
    except (OSError, yaml.YAMLError) as error:
        raise AccountCatalogError(f"Unable to read account contract {path.name}") from error
    if not isinstance(value, dict):
        raise AccountCatalogError(f"Account contract {path.name} must be a YAML mapping")
    return value


def _relative_child(root: Path, candidate: str, *, label: str) -> tuple[Path, str]:
    if not isinstance(candidate, str) or not candidate or Path(candidate).is_absolute():
        raise AccountCatalogError(f"{label} must be a non-empty relative path")
    resolved = (root / candidate).resolve()
    try:
        relative = resolved.relative_to(root)
    except ValueError as error:
        raise AccountCatalogError(f"{label} escapes its declared domain") from error
    return resolved, relative.as_posix()


def _destination_root(path: str) -> tuple[Path, str]:
    """Map only mounted domains; unknown workspace roots fail closed."""
    top_level, separator, remainder = path.partition("/")
    if not separator or not remainder:
        raise AccountCatalogError("Destination path must contain a domain and subdirectory")
    if top_level == "personal":
        return Path(settings.personal_memos_path).resolve().parents[1], remainder
    if top_level == "knowledge":
        return Path(settings.knowledge_root_path).resolve(), remainder
    raise AccountCatalogError(f"Destination domain {top_level!r} is not mounted for Account routing")


def _repository_for(path: str, repositories: list[dict[str, Any]]) -> str:
    candidates: list[tuple[int, str]] = []
    for repository in repositories:
        repository_id = repository.get("id")
        repository_path = repository.get("path")
        if not isinstance(repository_id, str) or not isinstance(repository_path, str):
            continue
        # `.` is the declarative root-workspace owner, not an empty/missing
        # repository path.  It is the legitimate owner for Personal and
        # Knowledge destinations that are not independent nested repositories.
        normalized = repository_path.strip("/")
        if normalized in {"", "."}:
            candidates.append((0, repository_id))
        elif path == normalized or path.startswith(f"{normalized}/"):
            candidates.append((len(normalized), repository_id))
    if not candidates:
        raise AccountCatalogError(f"No registered repository owns destination {path}")
    return max(candidates)[1]


def _fingerprint(paths: list[Path]) -> str:
    """Hash exact mounted contracts without disclosing their contents."""
    digest = hashlib.sha256()
    # Label each byte stream with its stable contract-relative identity so the
    # same text in a different role cannot produce an ambiguous fingerprint.
    for path in sorted(paths, key=lambda item: str(item)):
        try:
            content = path.read_bytes()
        except OSError as error:
            raise AccountCatalogError("Unable to read account contract") from error
        digest.update(path.name.encode("utf-8"))
        digest.update(b"\0")
        digest.update(content)
        digest.update(b"\0")
    return digest.hexdigest()


def validate_account_catalog() -> CatalogValidationResult:
    """Fully validate the Account Catalog and return one authorization snapshot.

    This is deliberately synchronous and side-effect free so triage and
    acceptance can fail closed at the moment they need authority, not merely
    rely on the metadata endpoint having succeeded earlier.
    """
    root_manifest_path = Path(settings.account_workspace_manifest_path)
    catalog_path = Path(settings.account_catalog_path)
    repositories_path = Path(settings.account_repository_registry_path)
    root_manifest = _load_yaml(root_manifest_path)
    matrix = root_manifest.get("configuration_matrix")
    if not isinstance(matrix, dict):
        raise AccountCatalogError("Root manifest has no configuration_matrix")
    if matrix.get("account_catalog") != "registry/account_catalog.yaml":
        raise AccountCatalogError("Root manifest does not declare the expected account catalog")
    if matrix.get("repository_registry") != "registry/repositories.yaml":
        raise AccountCatalogError("Root manifest does not declare the expected repository registry")

    catalog = _load_yaml(catalog_path)
    repository_index = _load_yaml(repositories_path)
    repositories = repository_index.get("repositories")
    if not isinstance(repositories, list):
        raise AccountCatalogError("Repository registry has no repositories list")
    schema_version = catalog.get("schema_version")
    entries = catalog.get("destinations")
    if schema_version != "1.0" or not isinstance(entries, list):
        raise AccountCatalogError("Account catalog must use schema_version 1.0 and destinations list")

    destinations: list[AccountDestination] = []
    fingerprint_paths = [root_manifest_path, catalog_path, repositories_path]
    seen_ids: set[str] = set()
    for entry in entries:
        if not isinstance(entry, dict):
            raise AccountCatalogError("Account destination must be a mapping")
        destination_id = entry.get("id")
        if not isinstance(destination_id, str) or not destination_id or destination_id in seen_ids:
            raise AccountCatalogError("Account destination IDs must be unique non-empty strings")
        seen_ids.add(destination_id)
        declared_path = entry.get("path")
        if not isinstance(declared_path, str):
            raise AccountCatalogError(f"Destination {destination_id} needs a path")
        domain_root, relative_destination = _destination_root(declared_path)
        destination_path, _ = _relative_child(domain_root, relative_destination, label=f"destination {destination_id}")
        manifest_path = destination_path / "manifest.yaml"
        if not destination_path.is_dir() or not manifest_path.is_file():
            raise AccountCatalogError(f"Destination {destination_id} needs a directory and manifest.yaml")
        manifest = _load_yaml(manifest_path)
        fingerprint_paths.append(manifest_path)
        expected_manifest = entry.get("manifest")
        if not isinstance(expected_manifest, dict) or not expected_manifest:
            raise AccountCatalogError(f"Destination {destination_id} needs manifest assertions")
        if any(manifest.get(key) != value for key, value in expected_manifest.items()):
            raise AccountCatalogError(f"Destination {destination_id} manifest assertions do not match")

        privacy = entry.get("privacy")
        capabilities = entry.get("proposal_capabilities")
        context_paths = entry.get("readable_context")
        enabled = entry.get("enabled", True)
        if privacy not in {"personal_only", "objective_reference"}:
            raise AccountCatalogError(f"Destination {destination_id} has invalid privacy classification")
        if not isinstance(capabilities, list) or not capabilities or not all(isinstance(item, str) and item for item in capabilities):
            raise AccountCatalogError(f"Destination {destination_id} needs proposal capabilities")
        if not isinstance(context_paths, list) or not all(isinstance(item, str) and item for item in context_paths):
            raise AccountCatalogError(f"Destination {destination_id} has invalid readable_context")
        if not isinstance(enabled, bool):
            raise AccountCatalogError(f"Destination {destination_id} has invalid enabled state")

        resources: list[CatalogContextResource] = []
        for context_path in context_paths:
            context_file, context_relative = _relative_child(destination_path, context_path, label=f"destination {destination_id} context")
            if not context_file.is_file():
                raise AccountCatalogError(f"Destination {destination_id} context file is missing")
            fingerprint_paths.append(context_file)
            resources.append(CatalogContextResource(path=context_relative))
        # Disabled entries are still structurally validated and fingerprinted;
        # they are simply absent from the usable authorization projection.
        if not enabled:
            continue
        destinations.append(AccountDestination(
            id=destination_id,
            path=declared_path,
            repository_id=_repository_for(declared_path, repositories),
            privacy=privacy,
            readable_context=resources,
            proposal_capabilities=sorted(set(capabilities)),
        ))
    fingerprint = _fingerprint(fingerprint_paths)
    response = AccountCatalogResponse(
        schema_version=schema_version,
        catalog_path="registry/account_catalog.yaml",
        catalog_fingerprint=fingerprint,
        destinations=destinations,
    )
    return CatalogValidationResult(
        catalog=response,
        catalog_fingerprint=fingerprint,
        destinations_by_id={destination.id: destination for destination in destinations},
    )


def load_account_catalog() -> AccountCatalogResponse:
    """Backward-compatible metadata projection of the full validation result."""
    return validate_account_catalog().catalog
