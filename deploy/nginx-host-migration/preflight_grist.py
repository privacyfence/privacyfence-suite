"""Read-only report on the old Grist's home database, for migrate.sh preflight.

migrate.sh pipes this file into `python3 -` inside the old Grist container. Arguments:
HOME_DB TEAM_SITE ADMIN_EMAIL ALLOWED_DOMAIN "HTPASSWD NAMES". It prints `ok`, `WARN`, `FAIL` and
`info` lines; migrate.sh counts the WARN and FAIL lines. Standard library only (the container's Python).
"""

import sqlite3
import sys


def report(homedb: str, site: str, admin: str, domain: str, htnames: str) -> list[str]:
    db = sqlite3.connect(f"file:{homedb}?mode=ro", uri=True)

    def q(sql: str, *args: object) -> list[tuple]:
        return db.execute(sql, args).fetchall()

    lines = []
    emails = dict(q("select user_id, email from logins"))
    docs = dict(
        q(
            "select w.org_id, count(*) from docs d join workspaces w on w.id = d.workspace_id "
            "where d.removed_at is null and w.removed_at is null group by w.org_id"
        )
    )

    lines.append("  info  Grist sites (documents):")
    team = None
    for oid, odomain, name, owner in q("select id, domain, name, owner_id from orgs order by id"):
        kind = f"personal site of {emails.get(owner, f'user {owner}')}" if owner else "team site"
        lines.append(f"          {odomain or '-'}  '{name}'  {kind}  docs={docs.get(oid, 0)}")
        if not owner and odomain == site:
            team = oid
        if owner and docs.get(oid, 0):
            lines.append(
                f"  WARN  {docs[oid]} document(s) in the personal site of {emails.get(owner)}: with "
                "GRIST_SINGLE_ORG they are no longer shown; move them to the team site first"
            )

    if not site:
        lines.append("  FAIL  GRIST_TEAM_SITE is empty")
    elif team is None:
        lines.append(
            f"  WARN  no team site '{site}': Grist creates an empty one for GRIST_ADMIN_EMAIL; set "
            "GRIST_TEAM_SITE to the existing site's domain to keep its documents in view"
        )
    else:
        owners = [
            email
            for (email,) in q(
                "select l.email from acl_rules r join groups g on g.id = r.group_id "
                "join group_users gu on gu.group_id = g.id join logins l on l.user_id = gu.user_id "
                "where r.org_id = ? and g.name = 'owners'",
                team,
            )
        ]
        if admin.lower() in (o.lower() for o in owners):
            lines.append(f"  ok    {admin} owns team site '{site}'")
        else:
            lines.append(
                f"  FAIL  GRIST_ADMIN_EMAIL={admin or '(empty)'} does not own team site '{site}' "
                f"(owners: {', '.join(owners) or 'none'})"
            )

    users = sorted(set(emails.values()))
    lines.append(f"  info  {len(users)} Grist login(s); sign-in through PrivacyFence matches them by email")
    if domain:
        outside = [
            e
            for e in users
            if not e.lower().endswith("@" + domain.lower()) and not e.lower().endswith(("@getgrist.com", "localhost"))
        ]
        if outside:
            lines.append(
                f"  WARN  {len(outside)} login(s) not in ALLOWED_DOMAIN cannot sign in through PrivacyFence: "
                + ", ".join(outside)
            )

    names = htnames.split()
    if names:
        known = {e.lower() for e in users}
        for name in names:
            if "@" not in name:
                lines.append(
                    f"  WARN  htpasswd user '{name}' is not an email address: rename that person's Grist "
                    "login to their email first, or their documents stay with the old user"
                )
            elif name.lower() not in known:
                lines.append(f"  info  htpasswd user '{name}' has no Grist login yet (never signed in)")
        lines.append(f"  ok    {len(names)} htpasswd user(s) compared")
    return lines


def main(argv: list[str]) -> int:
    args = (argv + [""] * 5)[:5]
    print("\n".join(report(*args)))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
