"""The project library (a directory of ``<id>.json`` files) on its own, without the API."""

import json
import os
import threading
from datetime import timedelta
from pathlib import Path

import pytest

from mcda_studio.domain.errors import (
    ProjectExistsError,
    ProjectLoadError,
    ProjectNotFoundError,
    StaleRevisionError,
)
from mcda_studio.services import project_service as ps
from mcda_studio.storage.project_store import (
    TRASH_DIR,
    InvalidProjectIdError,
    ProjectStore,
)

from builders import tiny_project


@pytest.fixture
def store(tmp_path: Path) -> ProjectStore:
    return ProjectStore(tmp_path / "library")


def named(project_id: str, title: str = "T"):  # type: ignore[no-untyped-def]
    p = tiny_project()
    p.id = project_id
    p.title = title
    return p


class TestIdentity:
    def test_the_file_is_named_after_the_project_id(self, store: ProjectStore) -> None:
        store.create(named("alpha"))
        assert (store.root / "alpha.json").is_file()

    @pytest.mark.parametrize(
        "bad", ["", "../escape", "a/b", "a\\b", ".hidden", "-lead", "x" * 65, "sp ace", "ü"]
    )
    def test_an_id_that_could_not_be_a_safe_file_name_is_refused_everywhere(
        self, store: ProjectStore, bad: str
    ) -> None:
        for operation in (store.path_for, store.exists, store.get, store.delete):
            with pytest.raises(InvalidProjectIdError):
                operation(bad)

    def test_nothing_is_ever_written_outside_the_library(
        self, store: ProjectStore, tmp_path: Path
    ) -> None:
        with pytest.raises(InvalidProjectIdError):
            store.path_for("../outside")
        assert not (tmp_path / "outside.json").exists()

    def test_a_file_whose_inner_id_disagrees_with_its_name_is_unreadable_not_silently_adopted(
        self, store: ProjectStore
    ) -> None:
        store.create(named("alpha"))
        (store.root / "alpha.json").rename(store.root / "beta.json")
        with pytest.raises(ProjectLoadError, match="must agree"):
            store.get("beta")
        found, unreadable = store.list()
        assert found == []
        assert [u.file for u in unreadable] == ["beta.json"]


class TestCreateAndGet:
    def test_roundtrip_is_exact_and_the_fingerprint_matches_the_project(
        self, store: ProjectStore
    ) -> None:
        p = named("alpha")
        created = store.create(p)
        loaded = store.get("alpha")
        assert loaded.project == p
        assert loaded.fingerprint == created.fingerprint == p.fingerprint()

    def test_create_never_overwrites(self, store: ProjectStore) -> None:
        store.create(named("alpha", "first"))
        with pytest.raises(ProjectExistsError):
            store.create(named("alpha", "second"))
        assert store.get("alpha").project.title == "first"

    def test_missing_project(self, store: ProjectStore) -> None:
        with pytest.raises(ProjectNotFoundError):
            store.get("nope")
        assert store.exists("nope") is False

    def test_the_library_directory_is_created_on_first_write(self, tmp_path: Path) -> None:
        s = ProjectStore(tmp_path / "does" / "not" / "exist")
        assert s.list() == ([], [])
        s.create(named("alpha"))
        assert s.exists("alpha")


class TestReplace:
    def test_replace_overwrites_and_changes_the_fingerprint(self, store: ProjectStore) -> None:
        first = store.create(named("alpha", "one"))
        second = store.replace(named("alpha", "two"))
        assert second.project.title == "two"
        assert second.fingerprint != first.fingerprint

    def test_replace_of_a_project_that_is_not_stored_is_refused(self, store: ProjectStore) -> None:
        with pytest.raises(ProjectNotFoundError):
            store.replace(named("ghost"))
        assert not (store.root / "ghost.json").exists()

    def test_conditional_replace_succeeds_on_the_revision_the_caller_saw(
        self, store: ProjectStore
    ) -> None:
        seen = store.create(named("alpha", "one"))
        store.replace(named("alpha", "two"), expected_fingerprint=seen.fingerprint)
        assert store.get("alpha").project.title == "two"

    def test_conditional_replace_refuses_a_stale_revision_and_writes_nothing(
        self, store: ProjectStore
    ) -> None:
        seen = store.create(named("alpha", "one"))
        store.replace(named("alpha", "theirs"))  # someone else saved meanwhile
        before = (store.root / "alpha.json").read_bytes()
        with pytest.raises(StaleRevisionError):
            store.replace(named("alpha", "mine"), expected_fingerprint=seen.fingerprint)
        assert (store.root / "alpha.json").read_bytes() == before

    def test_two_writers_with_the_same_base_cannot_both_win(self, store: ProjectStore) -> None:
        base = store.create(named("alpha", "base"))
        outcomes: list[str] = []
        barrier = threading.Barrier(8)

        def writer(n: int) -> None:
            barrier.wait()
            try:
                store.replace(named("alpha", f"writer {n}"), expected_fingerprint=base.fingerprint)
                outcomes.append("won")
            except StaleRevisionError:
                outcomes.append("stale")

        threads = [threading.Thread(target=writer, args=(i,)) for i in range(8)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()
        assert outcomes.count("won") == 1
        assert outcomes.count("stale") == 7


class TestListing:
    def test_lists_projects_most_recently_modified_first(self, store: ProjectStore) -> None:
        for i, pid in enumerate(["old", "mid", "new"]):
            store.create(named(pid, pid))
            stamp = 1_700_000_000 + i * 100
            os.utime(store.root / f"{pid}.json", (stamp, stamp))
        found, unreadable = store.list()
        assert [s.project.id for s in found] == ["new", "mid", "old"]
        assert unreadable == []
        assert found[0].updated_at - found[2].updated_at == timedelta(seconds=200)

    def test_unreadable_files_are_reported_not_hidden_and_do_not_block_the_rest(
        self, store: ProjectStore
    ) -> None:
        store.create(named("good"))
        (store.root / "broken.json").write_text("{not json", encoding="utf-8")
        (store.root / "future.json").write_text(
            json.dumps(
                {
                    **json.loads((store.root / "good.json").read_text()),
                    "schema_version": 99,
                    "id": "future",
                }
            ),
            encoding="utf-8",
        )
        found, unreadable = store.list()
        assert [s.project.id for s in found] == ["good"]
        assert sorted(u.file for u in unreadable) == ["broken.json", "future.json"]
        assert all(u.error for u in unreadable)

    def test_hidden_files_and_the_trash_are_not_projects(self, store: ProjectStore) -> None:
        store.create(named("good"))
        (store.root / ".draft.json").write_text("{}", encoding="utf-8")
        store.delete("good")
        assert store.list() == ([], [])


class TestDelete:
    def test_delete_moves_the_file_to_the_trash_intact(self, store: ProjectStore) -> None:
        store.create(named("alpha", "keep me"))
        original = (store.root / "alpha.json").read_bytes()
        target = store.delete("alpha")
        assert not store.exists("alpha")
        assert target.parent == store.root / TRASH_DIR
        assert target.read_bytes() == original

    def test_deleting_twice_keeps_both_copies(self, store: ProjectStore) -> None:
        store.create(named("alpha"))
        first = store.delete("alpha")
        store.create(named("alpha"))
        second = store.delete("alpha")
        assert first != second
        assert first.exists() and second.exists()

    def test_a_deleted_id_can_be_created_again(self, store: ProjectStore) -> None:
        store.create(named("alpha", "one"))
        store.delete("alpha")
        store.create(named("alpha", "two"))
        assert store.get("alpha").project.title == "two"

    def test_deleting_a_missing_project_is_an_error(self, store: ProjectStore) -> None:
        with pytest.raises(ProjectNotFoundError):
            store.delete("nope")


def test_stored_projects_are_independent_copies(store: ProjectStore) -> None:
    store.create(named("alpha"))
    a = store.get("alpha").project
    a.title = "mutated in memory"
    assert store.get("alpha").project.title == "T"
    assert ps.duplicate_project(a).id != a.id
