"""Recovery properties: no overwrite, no escapes and no loss of recovery data on failures."""

import os

import pytest

from mcda_studio.domain.errors import ProjectExistsError
from mcda_studio.storage.library_lock import LibraryBusyError, LibraryLockError, LibraryOwnership
from mcda_studio.storage.project_store import (
    InvalidTrashEntryError,
    ProjectStore,
    RestoreError,
    UnreadableTrashEntryError,
)

from builders import tiny_project


def deleted(tmp_path):
    store = ProjectStore(tmp_path / "library")
    project = tiny_project()
    store.create(project)
    entry = store.delete(project.id)
    return store, project, entry


def test_delete_list_restore_reopens_identical_project_and_retains_recovery(tmp_path):
    store, project, entry = deleted(tmp_path)
    before = entry.read_bytes()
    row = store.list_trash()[0]
    assert row.entry == entry.name and row.title == project.title
    assert row.deleted_at is not None and row.readable and not row.conflict
    restored = store.restore(entry.name)
    assert restored.project == project and restored.fingerprint == project.fingerprint()
    assert ProjectStore(store.root).get(project.id) == restored
    assert entry.read_bytes() == before
    assert store.list_trash()[0].conflict


def test_restore_conflict_never_overwrites_and_copy_gets_new_identity(tmp_path):
    store, project, entry = deleted(tmp_path)
    active = project.model_copy(update={"title": "Active revision"})
    store.create(active)
    before = (store.root / f"{project.id}.json").read_bytes()
    with pytest.raises(ProjectExistsError):
        store.restore(entry.name)
    assert (store.root / f"{project.id}.json").read_bytes() == before
    copied = store.restore(entry.name, as_copy=True)
    assert copied.project.id != project.id and copied.fingerprint != project.fingerprint()
    assert copied.project.model_copy(update={"id": project.id}) == project
    assert entry.exists() and store.get(project.id).project == active


@pytest.mark.parametrize(
    "entry",
    ["../outside.json", "/tmp/outside.json", "a/b.json", "x.json", "x.20269999T999999999999Z.json"],
)
def test_unsafe_entry_names_refused_before_writes(tmp_path, entry):
    store = ProjectStore(tmp_path / "library")
    with pytest.raises(InvalidTrashEntryError):
        store.restore(entry)
    assert not store.root.exists()


def test_unreadable_and_mismatched_entries_visible_and_retained(tmp_path):
    store, project, entry = deleted(tmp_path)
    entry.write_text("{broken json")
    assert not store.list_trash()[0].readable
    with pytest.raises(UnreadableTrashEntryError):
        store.restore(entry.name)
    assert entry.read_text() == "{broken json"
    entry.write_text(project.model_copy(update={"id": "wrong"}).model_dump_json())
    with pytest.raises(InvalidTrashEntryError, match="must agree"):
        store.restore(entry.name)
    assert entry.exists() and store.list_trash()[0].error


def test_symlink_entry_and_symlink_trash_directory_cannot_escape(tmp_path):
    store, project, entry = deleted(tmp_path)
    outside = tmp_path / "outside.json"
    entry.rename(outside)
    entry.symlink_to(outside)
    before = outside.read_bytes()
    assert not store.list_trash()[0].readable
    with pytest.raises(UnreadableTrashEntryError):
        store.restore(entry.name)
    assert outside.read_bytes() == before
    entry.unlink()
    entry.parent.rmdir()
    entry.parent.symlink_to(tmp_path, target_is_directory=True)
    with pytest.raises(InvalidTrashEntryError):
        store.list_trash()
    with pytest.raises(InvalidTrashEntryError):
        store.restore(entry.name)
    assert outside.read_bytes() == before


def test_existing_destination_symlink_is_not_followed_or_replaced(tmp_path):
    store, project, entry = deleted(tmp_path)
    outside = tmp_path / "unrelated.json"
    outside.write_text("keep")
    destination = store.root / f"{project.id}.json"
    destination.symlink_to(outside)
    with pytest.raises(ProjectExistsError):
        store.restore(entry.name)
    assert destination.is_symlink() and outside.read_text() == "keep"
    assert entry.exists()


@pytest.mark.parametrize("failure", ["stage", "link", "directory-sync"])
def test_failure_preserves_original_recovery_and_active_projects(tmp_path, monkeypatch, failure):
    from mcda_studio.storage import project_store as module

    store, project, entry = deleted(tmp_path)
    before = entry.read_bytes()
    sync = os.fsync
    if failure == "stage":
        monkeypatch.setattr(
            module, "to_json_text", lambda p: (_ for _ in ()).throw(OSError("disk full"))
        )
    elif failure == "link":
        monkeypatch.setattr(
            module.os, "link", lambda *a, **k: (_ for _ in ()).throw(OSError("link failed"))
        )
    else:
        import stat

        def fail_directory(fd):
            if stat.S_ISDIR(os.fstat(fd).st_mode):
                raise OSError("directory sync failed")
            return sync(fd)

        monkeypatch.setattr(module.os, "fsync", fail_directory)
    with pytest.raises(RestoreError, match="retained"):
        store.restore(entry.name)
    assert entry.read_bytes() == before
    destination = store.root / f"{project.id}.json"
    if destination.exists():
        assert store.get(project.id).project == project
    assert not list(store.root.glob(".restore-*.tmp"))


def test_non_regular_recovery_file_cannot_block_listing(tmp_path):
    store, project, entry = deleted(tmp_path)
    entry.unlink()
    os.mkfifo(entry)
    assert not store.list_trash()[0].readable
    with pytest.raises(InvalidTrashEntryError):
        store.restore(entry.name)


def test_owner_reentrancy_and_failed_acquire_cannot_bypass_lock(tmp_path):
    root = tmp_path / "library"
    first, second = ProjectStore(root), ProjectStore(root)
    with first.ownership(port=9876):
        first.create(tiny_project())  # Same owner's worker writes do not acquire a second fd.
        for _ in range(2):
            with pytest.raises(LibraryBusyError, match="9876"):
                second.create(tiny_project())
    with second.ownership():
        assert second.list()[0]


def test_stale_diagnostics_do_not_own_library_and_symlink_lock_is_refused(tmp_path):
    root = tmp_path / "library"
    with LibraryOwnership(root):
        pass
    (root / ".mcda-studio.lock").write_text('{"pid":99999,"port":1234}')
    with LibraryOwnership(root):
        pass
    (root / ".mcda-studio.lock").unlink()
    target = tmp_path / "do-not-touch"
    target.write_text("original")
    (root / ".mcda-studio.lock").symlink_to(target)
    with pytest.raises(LibraryLockError), LibraryOwnership(root):
        pass
    assert target.read_text() == "original"
