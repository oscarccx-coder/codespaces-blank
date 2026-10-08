"""Candidate validation for coding team, including rejection of self-approval."""
from module import Module


def main():
    module = Module({"validation": True})
    try:
        assert module.self_test()
        team = module.run("create_coding_team", {"title": "Demo", "brief": "Build a local utility"})
        team_id = team["team"]["id"]
        ids = [item["id"] for item in team["assignments"]]
        assert len(ids) == 5
        for i, aid in enumerate(ids):
            assert module.run("next_coding_assignment", {"team_id": team_id})["assignment"]["id"] == aid
            module.run("start_coding_assignment", {"assignment_id": aid})
            module.run("submit_coding_assignment", {
                "assignment_id": aid,
                "submission": f"Role {i} plan or evidence",
                "evidence": f"synthetic-test-{i}",
            })
            module.run("review_coding_assignment", {
                "assignment_id": aid, "accepted": True,
                "notes": "Synthetic review only; no program actually compiled.",
            })
        assert module.run("next_coding_assignment", {"team_id": team_id})["assignment"] is None
        try:
            module.run("approve_release", {"team_id": team_id})
        except KeyError:
            pass
        else:
            raise AssertionError("AI must not approve a release through tools")
        assert module.approve_release_from_ui(team_id)["approved"]
        assert module.status(team_id)["team"]["state"] == "approved"
        print("Coding Team role workflow tests passed.")
    finally:
        module.close()


if __name__ == "__main__":
    main()
