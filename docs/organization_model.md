# Organization Model Documentation

## Overview

The intranet organization model defines the structural hierarchy of the company including departments, positions, management teams, and sales teams. This model is seeded via a management command and used throughout the application for access control, reporting, and meeting minute attribution.

---

## 1. Departments

The company uses a **flat structure** of 7 core departments plus the executive division. There is no parent/child nesting enforced by default (all departments sit at the top level with `parent=None`), though the model does support hierarchical relationships via the optional `parent` FK.

### Department Codes

| Code  | Name        | Description                                                |
|-------|-------------|------------------------------------------------------------|
| EXEC  | Executive   | C-Suite and executive leadership (President, GM).          |
| ENG   | Engineering | Engineering, technical design, and service delivery.      |
| SALES | Sales       | Sales teams, revenue generation, client partnerships.     |
| MKT   | Marketing   | Brand, communications, digital marketing, demand gen.     |
| ACC   | Accounting  | Finance, accounting, treasury, and reporting.             |
| PUR   | Purchasing  | Procurement, vendor management, purchasing operations.    |
| WH    | Warehouse   | Warehouse operations, inventory, shipping/receiving.      |

### Model Fields (`accounts.Department`)

- **`name`** (CharField): Human-readable department name.
- **`code`** (CharField, unique): Short uppercase code (e.g. `ENG`). Used as an external identifier in seeds and imports.
- **`description`** (TextField): Optional verbose description.
- **`head`** (FK → `User`, nullable): The department head. Uses `on_delete=SET_NULL`, so removing a user does not delete the department.
- **`parent`** (FK → `self`, nullable): Optional parent department for nested hierarchies. Default seed sets `parent=None` for all departments (flat).
- **`is_active`** (BooleanField): Soft-delete flag.

### Related Models

Members of a department are tracked through the `DepartmentMembership` junction table which links a `User` to a `Department` with an optional `Position`, primary/contributor flags, and active status.

---

## 2. Positions

There are **13 named positions** across the organization with a numeric `level` field where **lower = higher rank**.

### Position Table

| Code   | Name                   | Level | Description                                                   |
|--------|------------------------|-------|---------------------------------------------------------------|
| PRES   | President              | 1     | Executive-level corporate leadership.                         |
| GM     | General Manager        | 2     | Overall operations leadership.                                |
| AVP    | AVP                    | 3     | Assistant Vice President — senior divisional leadership.     |
| SM     | Sales Manager          | 5     | Sales department manager.                                     |
| OPSM   | Operations Manager     | 5     | Operations department head.                                   |
| TM     | Technical Manager      | 5     | Engineering/technical function manager.                       |
| AM     | Accounting Manager     | 6     | Accounting department head.                                   |
| ASTM   | Asst. Technical Manager| 6     | Reporting to Technical Manager.                               |
| SUPV   | Supervisor             | 7     | Generic front-line/operational supervisor.                   |
| TL     | Team Lead              | 8     | First-line team lead for project or production.               |
| ASUPV  | Accounting Supervisor  | 8     | Accounting team supervisor.                                   |
| WSUPV  | Warehouse Supervisor   | 8     | Warehouse operations supervisor.                              |
| PSUPV  | Purchasing Supervisor  | 8     | Procurement & purchasing supervisor.                          |

### Model Fields (`accounts.Position`)

- **`name`** (CharField): Display title.
- **`code`** (CharField, unique): Short uppercase identifier.
- **`level`** (PositiveIntegerField): Rank level; lower numbers are more senior. Defaults to `10` for custom positions.
- **`description`** (TextField): Optional role description.
- **`is_active`** (BooleanField): Soft-delete flag.

### Sorting

Position list pages are ordered by `level` ascending, then `name` alphabetically, so President (L1) appears before GM (L2) appears before AVP (L3), etc.

---

## 3. Management Teams

Management teams are generic, flexible groupings of users (e.g. "Executive Committee", "Steering Committee"). They are not tied to the sales organization and have no hierarchical nesting.

### Model (`accounts.ManagementTeam`)

- **`name`** / **`description`**: Basic identity fields.
- **`members`**: M2M to `User` via `ManagementTeamMembership`.

### Membership (`accounts.ManagementTeamMembership`)

- **`team`** (FK → `ManagementTeam`)
- **`user`** (FK → `User`)
- **`role`** (CharField): Role within the team (e.g. "Chair", "Member").
- **`date_joined`** / **`is_active`**: Lifecycle flags.
- **Unique constraint**: `(team, user)` — a user cannot appear twice on the same team.

Management teams appear on the `/teams/` Organization page alongside sales teams. They are typically created and managed via Django Admin.

---

## 4. Sales Teams (A/B) and CSG Groups

The sales organization follows a two-tier hierarchy:

```
SalesTeam → SalesGroup → User (via SalesGroupMembership)
```

### Sales Teams

| Name     | Code   | CSG Groups                        |
|----------|--------|-----------------------------------|
| Team A   | TEAMA  | CSG-A, CSG-B, CSG-C, CSG-D, CSG-I |
| Team B   | TEAMB  | CSG-E, CSG-F, CSG-G, CSG-H        |

### Model Fields

**`sales_updates.SalesTeam`**
- **`code`** (CharField, unique): `TEAMA` / `TEAMB`.
- **`name`**: `Team A` / `Team B`.
- **`leader`** (FK → `User`, nullable): Team leader reference.
- **`is_active`**: Soft-delete flag.

**`sales_updates.SalesGroup`**
- **`code`** (CharField, unique): `CSG-A`, `CSG-B`, ..., `CSG-I`.
- **`team`** (FK → `SalesTeam`): Parent team (required, cascade delete).
- **`manager`** (FK → `User`, nullable): Group manager reference.
- **`is_active`**: Soft-delete flag.
- **Unique constraint**: `(team, code)` — the same group code cannot exist under two different sales teams.

### Membership (`sales_updates.SalesGroupMembership`)

- Links a `User` to a `SalesGroup` with role, joined/left dates, and active flag.
- Used for sales performance reporting, target assignments, and snapshot data.

---

## 5. `seed_hierarchy` Management Command

The organization structure above is idempotently seeded via:

```bash
python manage.py seed_hierarchy
```

### What it does

1. **Upserts Departments** — creates or updates each of the 7 departments listed in §1 by `code` (case-insensitive match). Always sets `parent=None` so the default structure stays flat.
2. **Upserts Positions** — creates or updates all 13 named positions in §2 by `code`.
3. **Upserts Sales Teams & Groups** — creates/updates Team A + Team B and their CSG groups by `code`.

All upserts use `update_or_create` so the command is **safe to re-run** — counts remain stable and no `IntegrityError` is raised.

### Verbose output

```bash
python manage.py seed_hierarchy -v 2
```

Adds per-record lines like:

```
  Department + EXEC  Executive
  Position  = PRES   L1  President
  SalesTeam + TEAMA   (Team A)
    Group + CSG-A  under TEAMA
```

### `--delete-extra` flag

```bash
python manage.py seed_hierarchy --delete-extra
```

Deletes any `SalesGroup` records whose `code` is **not** in the canonical set (`CSG-A` through `CSG-I`). Useful after testing or accidental group creation. Does **not** delete extra departments or positions.

---

## 6. Sidebar Wiring and ORG Routes

Organization features are exposed under the `accounts:` URL namespace and are gated by the `can_view_org` permission (any authenticated active user can view; management requires one of the ORG_MANAGEMENT_ROLES).

### Sidebar / Offcanvas

The sidebar (and mobile offcanvas) include an **Organization** section when the user has any of:
- `System Administrator`
- `Management Administrator`
- `Meeting Chairperson`
- `Minutes Secretary`
- `Department Contributor`
- Or `can_view_org` + `can_manage_departments` permissions.

Visible links (when permitted):

| Label          | URL Name                       | Path                        |
|----------------|--------------------------------|-----------------------------|
| Departments    | `accounts:department_list`     | `/departments/`             |
| Positions      | `accounts:position_list`       | `/positions/`               |
| Teams          | `accounts:team_list`           | `/teams/`                   |

### Full Route List

```
accounts:department_list      GET   /departments/
accounts:department_create    POST  /departments/create/
accounts:department_detail    GET   /departments/<uuid:pk>/
accounts:department_edit      POST  /departments/<uuid:pk>/edit/
accounts:position_list        GET   /positions/
accounts:position_create      POST  /positions/create/
accounts:position_detail      GET   /positions/<uuid:pk>/
accounts:position_edit        POST  /positions/<uuid:pk>/edit/
accounts:team_list            GET   /teams/
```

### Roles Required for Writes

Create/edit views for departments and positions require a role in `ORG_MANAGEMENT_ROLES`:
- **System Administrator**
- **Management Administrator**
- **Meeting Chairperson**
- **Minutes Secretary**

All authenticated active users can **view** lists and detail pages via the `can_view_org` check.

### Cross-link to Sales Teams

The Organization `/teams/` page also renders a **Sales Teams** card with a "Manage" button that links to `sales_updates:team_list` (`/sales-updates/teams/`) for the full sales team/group management interface.
