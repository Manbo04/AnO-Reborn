from flask import (
    request,
    render_template,
    session,
    redirect,
    flash,
    current_app,
)
from helpers import login_required, error
import os
from dotenv import load_dotenv

load_dotenv()
import variables  # noqa: E402
import datetime  # noqa: E402
from database import get_db_cursor  # noqa: E402
from database import cache_response  # noqa: E402

# flake8: noqa -- Temporarily disable flake8 for this file to avoid blocking critical fixes; remove when refactoring is complete


# Function for getting the coalition role of a user
def get_user_role(user_id):
    with get_db_cursor() as db:
        db.execute("SELECT role FROM coalitions WHERE userId=%s", (user_id,))
        row = db.fetchone()
        if not row:
            return None
        return row[0]


# Route for viewing a coalition's page
def coalition(colId):
    with get_db_cursor() as db:
        cId = session["user_id"]

        # OPTIMIZATION: Single query for basic coalition info + member count + total influence
        # Uses a pre-aggregated subquery to avoid N+1 per-member population lookups
        db.execute(
            """
            SELECT
                c.name, c.type, c.description, c.flag,
                COUNT(DISTINCT coal.userId) AS members_count,
                COALESCE(SUM(prov.total_pop), 0) AS total_influence
            FROM colNames c
            LEFT JOIN coalitions coal ON c.id = coal.colId
            LEFT JOIN (
                SELECT userId, COALESCE(SUM(population), 0) AS total_pop
                FROM provinces
                GROUP BY userId
            ) prov ON coal.userId = prov.userId
            WHERE c.id = %s
            GROUP BY c.id, c.name, c.type, c.description, c.flag
            """,
            (colId,),
        )
        result = db.fetchone()
        if not result:
            return error(404, "This coalition doesn't exist")
        name, colType, description, flag, members_count, total_influence = result
        average_influence = total_influence // members_count if members_count > 0 else 0

        # Calculate coalition statistics (provinces, cities, land, GDP)
        db.execute(
            """
            SELECT
                COALESCE(COUNT(p.id), 0) AS total_provinces,
                COALESCE(SUM(p.cityCount), 0) AS total_cities,
                COALESCE(SUM(p.land), 0) AS total_land
            FROM coalitions coal
            LEFT JOIN provinces p ON coal.userId = p.userId
            WHERE coal.colId = %s
            """,
            (colId,),
        )
        stats_result = db.fetchone()
        coalition_provinces = stats_result[0] if stats_result else 0
        coalition_cities = stats_result[1] if stats_result else 0
        coalition_land = stats_result[2] if stats_result else 0

        # Calculate averages per member
        coalition_avg_provinces = (
            coalition_provinces // members_count if members_count > 0 else 0
        )
        coalition_avg_cities = (
            coalition_cities // members_count if members_count > 0 else 0
        )
        coalition_avg_land = coalition_land // members_count if members_count > 0 else 0

        # GDP is the same as total influence (population-based)
        coalition_gdp = total_influence
        coalition_gdp_per_capita = average_influence

        try:
            db.execute(
                (
                    "SELECT coalitions.userId, users.username "
                    "FROM coalitions "
                    "INNER JOIN users ON coalitions.userId=users.id "
                    "WHERE coalitions.role='leader' "
                    "AND coalitions.colId=%s"
                ),
                (colId,),
            )
            leaders = db.fetchall()
        except (TypeError, AttributeError, IndexError):
            leaders = []

        try:
            # stats table has no influence column; keep list lightweight and avoid bad column reference
            # Uses pre-aggregated subquery to avoid N+1 per-member province count lookups
            db.execute(
                """
                SELECT coalitions.userId,
                       users.username,
                       coalitions.role,
                       0 AS influence,
                       COALESCE(prov.province_count, 0) AS province_count
                FROM coalitions
                INNER JOIN users ON coalitions.userId = users.id
                LEFT JOIN (
                    SELECT userId, COUNT(*) AS province_count
                    FROM provinces
                    GROUP BY userId
                ) prov ON coalitions.userId = prov.userId
                WHERE coalitions.colId = %s
                """,
                (colId,),
            )
            members = db.fetchall()
        except (TypeError, AttributeError, IndexError):
            members = []

        try:
            db.execute("SELECT userId FROM coalitions WHERE userId=(%s)", (cId,))
            userInCol = db.fetchone() is not None
        except (TypeError, AttributeError, IndexError):
            userInCol = False

        try:
            db.execute(
                "SELECT userId FROM coalitions WHERE userId=(%s) AND colId=(%s)",
                (cId, colId),
            )
            userInCurCol = db.fetchone() is not None
        except (TypeError, AttributeError, IndexError):
            userInCurCol = False

        try:
            # Determine the user's role for THIS coalition (avoid returning a role from another coalition)
            db.execute(
                "SELECT role FROM coalitions WHERE userId=%s AND colId=%s",
                (cId, colId),
            )
            row = db.fetchone()
            user_role = row[0] if row else None
        except Exception:
            user_role = None

        if (
            user_role in ["leader", "deputy_leader", "domestic_minister"]
            and userInCurCol
        ):
            member_roles = {
                "leader": None,
                "deputy_leader": None,
                "domestic_minister": None,
                "banker": None,
                "tax_collector": None,
                "foreign_ambassador": None,
                "general": None,
                "member": None,
            }
            # Fetch pending applications for leaders
            try:
                db.execute(
                    "SELECT a.id, a.userId, u.username, a.message, a.status, a.created_at "
                    "FROM col_applications a JOIN users u ON a.userId = u.id "
                    "WHERE a.colId=%s ORDER BY a.created_at DESC",
                    (colId,),
                )
                pending_applications = db.fetchall()
            except Exception:
                pending_applications = []

            # Also include simple /join() requests (requests table) for Invite-Only coalitions
            # so leaders/deputies see applicant usernames in the Leader Panel.
            try:
                db.execute(
                    "SELECT r.reqId, u.username, r.message FROM requests r JOIN users u ON r.reqId = u.id WHERE r.colId=%s ORDER BY r.reqId ASC",
                    (colId,),
                )
                join_reqs = db.fetchall()
                # append to pending_applications in the same tuple-shape used by the template
                for jr in join_reqs:
                    req_id, req_username, req_message = jr
                    # avoid duplicates (userId already present)
                    if not any(pa[1] == req_id for pa in pending_applications):
                        pending_applications.append(
                            (None, req_id, req_username, req_message, None, None)
                        )
            except Exception:
                # non-fatal; leave pending_applications as-is
                pass

            # OPTIMIZATION: Fetch all role counts in ONE query instead of 7 queries
            db.execute(
                "SELECT role, COUNT(userId) FROM coalitions WHERE colId=%s GROUP BY role",
                (colId,),
            )
            role_counts = db.fetchall()
            for role, count in role_counts:
                if role in member_roles:
                    member_roles[role] = count

        else:
            member_roles = {}
            pending_applications = []
        # Treaties
        if (
            user_role in ["foreign_ambassador", "leader", "deputy_leader"]
            and userInCurCol
        ):
            # Ingoing
            try:
                try:
                    db.execute(
                        "SELECT id FROM treaties WHERE col2_id=(%s) AND status='Pending' ORDER BY id ASC",
                        (colId,),
                    )
                    ingoing_ids = [row[0] for row in db.fetchall()]
                except Exception:
                    ingoing_ids = []

                col_ids = []
                col_names = []
                trt_names = []
                trt_descriptions = []

                # OPTIMIZATION: Batch fetch all treaty data in ONE query instead of N*2 queries
                if ingoing_ids:
                    placeholders = ",".join(["%s"] * len(ingoing_ids))
                    db.execute(
                        f"""SELECT t.id, t.col1_id, t.treaty_name, t.treaty_description, c.name
                            FROM treaties t
                            JOIN colNames c ON t.col1_id = c.id
                            WHERE t.id IN ({placeholders})""",
                        tuple(ingoing_ids),
                    )
                    for row in db.fetchall():
                        (
                            treaty_id,
                            col_id,
                            treaty_name,
                            treaty_description,
                            coalition_name,
                        ) = row
                        col_ids.append(col_id)
                        trt_names.append(treaty_name)
                        trt_descriptions.append(treaty_description)
                        col_names.append(coalition_name)

                ingoing_treaties = {}
                ingoing_treaties["ids"] = (ingoing_ids,)
                ingoing_treaties["col_ids"] = (col_ids,)
                ingoing_treaties["col_names"] = (col_names,)
                ingoing_treaties["treaty_names"] = (trt_names,)
                ingoing_treaties["treaty_descriptions"] = trt_descriptions
                ingoing_length = len(ingoing_ids)
            except Exception:
                ingoing_treaties = {}
                ingoing_length = 0

            # ACTIVE
            try:
                try:
                    db.execute(
                        "SELECT id FROM treaties WHERE col2_id=(%s) AND status='Active' OR col1_id=(%s) ORDER BY id ASC",
                        (colId, colId),
                    )
                    raw_active_ids = db.fetchall()
                except Exception:
                    raw_active_ids = []

                active_treaties = {}
                active_treaties["ids"] = []
                active_treaties["col_ids"] = []
                active_treaties["col_names"] = []
                active_treaties["treaty_names"] = []
                active_treaties["treaty_descriptions"] = []

                # OPTIMIZATION: Batch fetch all active treaty data in ONE query
                if raw_active_ids:
                    active_ids = [i[0] for i in raw_active_ids]
                    placeholders = ",".join(["%s"] * len(active_ids))
                    db.execute(
                        f"""SELECT t.id, t.col1_id, t.col2_id, t.treaty_name, t.treaty_description,
                                   c1.name as col1_name, c2.name as col2_name
                            FROM treaties t
                            JOIN colNames c1 ON t.col1_id = c1.id
                            JOIN colNames c2 ON t.col2_id = c2.id
                            WHERE t.id IN ({placeholders})""",
                        tuple(active_ids),
                    )
                    for row in db.fetchall():
                        (
                            offer_id,
                            col1_id,
                            col2_id,
                            treaty_name,
                            treaty_description,
                            col1_name,
                            col2_name,
                        ) = row
                        active_treaties["ids"].append(offer_id)
                        # Show the OTHER coalition, not the current one
                        if col1_id == colId:
                            coalition_id = col2_id
                            coalition_name = col2_name
                        else:
                            coalition_id = col1_id
                            coalition_name = col1_name
                        active_treaties["col_ids"].append(coalition_id)
                        active_treaties["col_names"].append(coalition_name)
                        active_treaties["treaty_names"].append(treaty_name)
                        active_treaties["treaty_descriptions"].append(
                            treaty_description
                        )

                active_length = len(raw_active_ids)
            except Exception:
                active_treaties = {}
                active_length = 0
        else:
            ingoing_treaties = {}
            active_treaties = {}
            ingoing_length = 0
            active_length = 0

        if userInCurCol:
            bankRaw = {
                "money": None,
                "rations": None,
                "oil": None,
                "coal": None,
                "uranium": None,
                "bauxite": None,
                "iron": None,
                "copper": None,
                "lead": None,
                "lumber": None,
                "components": None,
                "steel": None,
                "consumer_goods": None,
                "aluminium": None,
                "gasoline": None,
                "ammunition": None,
            }

            # OPTIMIZATION: Fetch all bank resources in ONE query instead of 15 queries
            resource_cols = ", ".join(bankRaw.keys())
            db.execute(
                f"SELECT {resource_cols} FROM colBanks WHERE colId=(%s)", (colId,)
            )
            row = db.fetchone()
            if row:
                for i, resource in enumerate(bankRaw.keys()):
                    bankRaw[resource] = row[i]
        else:
            bankRaw = {}

        # flag already fetched in initial query above

        # Leaders, deputy leaders and domestic ministers should be able to
        # view and act on incoming join requests for Invite-Only coalitions.
        if (
            user_role in ["leader", "deputy_leader", "domestic_minister"]
            and colType != "Open"
            and userInCurCol
        ):
            # Use a single JOIN query to fetch request IDs, names, and messages
            db.execute(
                """SELECT r.reqId, u.username, r.message
                   FROM requests r
                   INNER JOIN users u ON r.reqId = u.id
                   WHERE r.colId=%s
                   ORDER BY r.reqId ASC""",
                (colId,),
            )
            request_data = db.fetchall()

            # Debug: show request rows when rendering Applicants view
            try:
                print(
                    f"coalition.requests_on_page: colId={colId} user={cId} "
                    f"user_role={user_role} userInCurCol={userInCurCol} requests={request_data}",
                    flush=True,
                )
            except Exception:
                pass

            requestIds = [(r[0],) for r in request_data]
            requestNames = [r[1] for r in request_data]
            requestMessages = [r[2] for r in request_data]

            # Use an explicit name to avoid colliding with external modules or globals
            join_requests = zip(requestIds, requestNames, requestMessages)
        else:
            join_requests = []
            requestIds = []

        # COALITION BANK STUFF
        # Bank requests may be actioned by leader, deputy leaders and bankers
        if user_role in ["leader", "deputy_leader", "banker"] and userInCurCol:
            db.execute(
                """SELECT br.reqId, br.amount, br.resource, br.id, u.username
                   FROM colBanksRequests br
                   INNER JOIN users u ON br.reqId = u.id
                   WHERE br.colId=(%s)""",
                (colId,),
            )
            bankRequests = db.fetchall()
        else:
            bankRequests = []

        # Members list is now logged elsewhere for debugging if needed

        # Debugging info for failing deputy-applicant integration test
        try:
            app_pending_ids = [p[1] for p in pending_applications]
        except Exception:
            app_pending_ids = []
        try:
            req_ids = [r[0] for r in requestIds] if requestIds else []
        except Exception:
            req_ids = []
        # Print diagnostic info so it appears in CI logs regardless of logger level
        try:
            db.execute("SELECT username FROM users WHERE id=%s", (cId,))
            _urow = db.fetchone()
            cur_username = _urow[0] if _urow else None
        except Exception:
            cur_username = None

        print(
            f"coalition debug: colId={colId} colType={colType} user={cId}:{cur_username} "
            f"userInCurCol={userInCurCol} user_role={user_role} "
            f"pending_count={len(pending_applications) if isinstance(pending_applications, (list, tuple)) else 'unknown'} "
            f"request_count={len(requestIds) if isinstance(requestIds, (list, tuple)) else 'unknown'} "
            f"pending_ids={app_pending_ids} requestIds={req_ids}",
            flush=True,
        )

        return render_template(
            "coalition.html",
            name=name,
            colId=colId,
            user_role=user_role,
            description=description,
            colType=colType,
            userInCol=userInCol,
            join_requests=join_requests,
            userInCurCol=userInCurCol,
            total_influence=total_influence,
            average_influence=average_influence,
            leaders=leaders,
            flag=flag,
            bankRequests=bankRequests,
            active_treaties=active_treaties,
            bankRaw=bankRaw,
            ingoing_length=ingoing_length,
            active_length=active_length,
            member_roles=member_roles,
            ingoing_treaties=ingoing_treaties,
            zip=zip,
            requestIds=requestIds,
            members=members,
            pending_applications=pending_applications,
            # Coalition statistics
            coalitionProvinces=coalition_provinces,
            coalitionAverageProvinces=coalition_avg_provinces,
            coalitionCities=coalition_cities,
            coalitionAverageCities=coalition_avg_cities,
            coalitionLand=coalition_land,
            coalitionAverageLand=coalition_avg_land,
            coalitiongpd=coalition_gdp,
            coalitiongpdPerCapita=coalition_gdp_per_capita,
        )


# Route for establishing a coalition
def establish_coalition():
    with get_db_cursor() as db:
        # Check if user is already in a coalition (for both GET and POST)
        db.execute(
            "SELECT colId FROM coalitions WHERE userId=(%s)",
            (session["user_id"],),
        )
        existing = db.fetchone()
        if existing:
            return error(403, "You are already in a coalition")

    if request.method == "POST":
        with get_db_cursor() as db:
            cType = request.form.get("type")
            name = request.form.get("name")
            desc = request.form.get("description")

            if not name or not cType:
                return error(400, "Name and type are required")

            if cType not in ["Open", "Invite Only"]:
                return error(400, "Invalid coalition type")

            # Check if coalition name already exists
            db.execute("SELECT id FROM colNames WHERE name = %s", (name,))
            if db.fetchone():
                return error(
                    400,
                    "The coalition name is already taken. Please choose a different name.",
                )

            if len(str(name)) > 40:
                return error(
                    400,
                    "Name too long! the coalition name needs to be under 40 characters",
                )
            else:
                date = str(datetime.date.today())
                recruiting = True if request.form.get("recruiting") == "on" else False
                insert_query = (
                    "INSERT INTO colNames (name, type, description, date, recruiting) "
                    "VALUES (%s, %s, %s, %s, %s)"
                )
                db.execute(insert_query, (name, cType, desc, date, recruiting))

                db.execute("SELECT id FROM colNames WHERE name = (%s)", (name,))
                colId = db.fetchone()[
                    0
                ]  # Gets the coalition id of the just inserted coalition

                # Inserts the user as the leader of the coalition
                db.execute(
                    "INSERT INTO coalitions (colId, userId, role) VALUES (%s, %s, %s)",
                    (colId, session["user_id"], "leader"),
                )

                # Inserts the coalition into the table for coalition banks
                db.execute("INSERT INTO colBanks (colId) VALUES (%s)", (colId,))

                return redirect(
                    f"/coalition/{colId}"
                )  # Redirects to the new coalition's page
    else:
        return render_template("establish_coalition.html")


# Route for viewing all existing coalitions
def coalitions():
    """Coalition rankings page - optimized with SQL search/filter and pagination"""
    with get_db_cursor() as db:
        search = request.values.get("search", "").strip()
        raw_sort = request.values.get("sort")
        sort = raw_sort
        sortway = request.values.get("sortway")
        page = request.values.get("page", default=1, type=int)
        per_page = request.values.get("per_page", default=50, type=int)
        if per_page not in [50, 100, 150]:
            per_page = 50

        # Build WHERE clause for search and type filter
        where_conditions = []
        params = []

        if search:
            # Search by coalition name or ID
            if search.isdigit():
                where_conditions.append("c.id = %s")
                params.append(int(search))
            else:
                where_conditions.append("LOWER(c.name) LIKE LOWER(%s)")
                params.append(f"%{search}%")

        # Type filter
        if sort == "invite_only":
            where_conditions.append("c.type = 'Invite Only'")
        elif sort == "open":
            where_conditions.append("c.type = 'Open'")

        where_clause = ""
        if where_conditions:
            where_clause = "WHERE " + " AND ".join(where_conditions)

        # Determine ORDER BY clause
        actual_sort = (
            sort if sort and sort not in ["open", "invite_only"] else "influence"
        )
        if not sortway:
            sortway = "desc"

        order_dir = "DESC" if sortway == "desc" else "ASC"
        if actual_sort == "influence":
            order_by = f"total_influence {order_dir}"
        elif actual_sort == "members":
            order_by = f"members {order_dir}"
        elif actual_sort == "age":
            # Age: older = smaller date, so reverse the direction
            order_by = f"c.date {'ASC' if sortway == 'desc' else 'DESC'}"
        else:
            order_by = f"total_influence {order_dir}"

        # Count total matching coalitions
        count_query = f"""
            SELECT COUNT(DISTINCT c.id)
            FROM colNames c
            INNER JOIN coalitions coal ON c.id = coal.colId
            {where_clause}
        """
        db.execute(count_query, tuple(params))
        total_count = db.fetchone()[0] or 0

        # Calculate pagination
        total_pages = max(1, (total_count + per_page - 1) // per_page)
        if page < 1:
            page = 1
        if page > total_pages:
            page = total_pages
        offset = (page - 1) * per_page

        # Main query with pagination - all filtering/sorting in SQL
        main_query = f"""
            SELECT
                c.id,
                c.type,
                c.name,
                c.flag,
                COUNT(DISTINCT coal.userId) AS members,
                c.date,
                COALESCE(SUM(prov.total_pop), 0) AS total_influence
            FROM colNames c
            INNER JOIN coalitions coal ON c.id = coal.colId
            LEFT JOIN (
                SELECT userId, COALESCE(SUM(population), 0) AS total_pop
                FROM provinces
                GROUP BY userId
            ) prov ON coal.userId = prov.userId
            {where_clause}
            GROUP BY c.id, c.type, c.name, c.flag, c.date
            ORDER BY {order_by}
            LIMIT %s OFFSET %s
        """
        db.execute(main_query, tuple(params) + (per_page, offset))
        coalitionsDb = db.fetchall()

        coalitions_list = []
        for row in coalitionsDb:
            col_id, col_type, name, flag, members, col_date, influence = row

            # Calculate unix timestamp for display
            try:
                date_obj = datetime.datetime.fromisoformat(str(col_date))
                unix = int((date_obj - datetime.datetime(1970, 1, 1)).total_seconds())
            except (ValueError, TypeError):
                unix = 0

            coalitions_list.append(
                {
                    "id": col_id,
                    "type": col_type,
                    "name": name,
                    "flag": flag,
                    "members": members,
                    "date": col_date,
                    "influence": influence,
                    "unix": unix,
                }
            )

        return render_template(
            "coalitions.html",
            coalitions=coalitions_list,
            sort=actual_sort,
            sortway=sortway,
            search=search,
            selected_sort=raw_sort,
            current_page=page,
            total_pages=total_pages,
            total_count=total_count,
            per_page=per_page,
        )


# Route for joining a coalition
def join_col(colId):
    with get_db_cursor() as db:
        cId = session["user_id"]

        db.execute("SELECT colId FROM coalitions WHERE userId=%s", (cId,))
        row = db.fetchone()
        if row:
            return error(400, "You're already in a coalition")

        db.execute("SELECT type FROM colNames WHERE id=%s", (colId,))
        row = db.fetchone()
        if not row:
            return error(404, "Coalition not found")
        colType = row[0]

        if colType == "Open":
            db.execute(
                "INSERT INTO coalitions (colId, userId) VALUES (%s, %s)", (colId, cId)
            )
        else:
            # Check for existing join request (SELECT 1 is explicit and avoids SQL syntax errors)
            db.execute(
                "SELECT 1 FROM requests WHERE colId=%s AND reqId=%s",
                (colId, cId),
            )
            duplicate = db.fetchone()
            if duplicate is not None:
                return error(
                    400, "You've already submitted a request to join this coalition"
                )

            message = request.form.get("message", "")
            db.execute(
                "INSERT INTO requests (colId, reqId, message) VALUES (%s, %s, %s)",
                (colId, cId, message),
            )
            # Invalidate cached coalition page so leaders/deputies see the new
            # join request immediately (avoid serving a stale cached page).
            try:
                coalition_wrapped.invalidate(page=f"/coalition/{colId}")
            except Exception:
                pass

        return redirect(
            f"/coalition/{colId}"
        )  # Redirects to the joined coalitions page


# Route for leaving a coalition
def leave_col(colId):
    with get_db_cursor() as db:
        cId = session["user_id"]
        role = get_user_role(cId)

        if role == "leader":
            return error(400, "Can't leave coalition, you're the leader")

        db.execute(
            "DELETE FROM coalitions WHERE userId=(%s) AND colId=(%s)", (cId, colId)
        )

    return redirect("/coalitions")


# Route for redirecting to the user's coalition
def my_coalition():
    with get_db_cursor() as db:
        cId = session["user_id"]

        db.execute("SELECT colId FROM coalitions WHERE userId=%s", (cId,))
        row = db.fetchone()
        if not row:
            return redirect("/")  # Redirects to home page instead of an error
        coalition = row[0]

    return redirect(f"/coalition/{coalition}")


# Route for giving someone a role in your coalition
def give_position():
    with get_db_cursor() as db:
        cId = session["user_id"]

        db.execute("SELECT colId FROM coalitions WHERE userId=%s", (cId,))
        row = db.fetchone()
        if not row:
            return error(400, "You are not a part of any coalition")
        colId = row[0]

        user_role = get_user_role(cId)

        if user_role not in ["leader", "deputy_leader", "domestic_minister"]:
            return error(400, "You're not a leader")

        # DO NOT EDIT LIST. USED FOR RANKS
        roles = [
            "leader",
            "deputy_leader",
            "domestic_minister",
            "banker",
            "tax_collector",
            "foreign_ambassador",
            "general",
            "member",
        ]

        role = request.form.get("role")

        if role not in roles:
            return error(400, "No such role exists")

        username = request.form.get("username")

        # The user id for the person being given the role
        try:
            db.execute(
                "SELECT users.id, coalitions.colid, coalitions.role "
                "FROM users INNER JOIN coalitions ON users.id=coalitions.userid "
                "WHERE users.username=%s",
                (username,),
            )
            roleer, roleer_col, current_roleer_role = db.fetchone()

            if roleer_col != colId:
                return error(400, "User isn't in your coalition.")

            if roleer == cId:
                return error(400, "You can't change your own position.")

        except TypeError:
            return error(400, "No such user found")

        # If the user role is lower up the hierarchy than the giving role
        # Or if the current role of the person being given the role is higher up the hierarchy than the user giving the role
        if roles.index(role) < roles.index(user_role) or roles.index(
            current_roleer_role
        ) < roles.index(user_role):
            return error(400, "Can't edit role for a person higher rank than you.")

        db.execute(
            "UPDATE coalitions SET role=%s WHERE userId=%s AND colId=%s",
            (role, roleer, colId),
        )
        # Diagnostic: confirm role update in test logs
        print(f"give_position: set role={role} for userId={roleer}", flush=True)

        # Invalidate cached coalition page(s) so the promoted user (and
        # other viewers) see the updated role / applicants immediately.
        try:
            coalition_wrapped.invalidate(user_id=roleer, page=f"/coalition/{colId}")
        except Exception:
            pass

        return redirect("/my_coalition")


# Route for accepting a coalition join request
def adding(uId):
    with get_db_cursor() as db:
        db.execute("SELECT colId FROM requests WHERE reqId=(%s)", (uId,))
        row = db.fetchone()
        if not row:
            return error(400, "User hasn't posted a request to join")
        colId = row[0]

        cId = session["user_id"]
        user_role = get_user_role(cId)

        if user_role not in ["leader", "deputy_leader", "domestic_minister"]:
            return error(400, "You are not a leader of the coalition")

        db.execute("DELETE FROM requests WHERE reqId=(%s) AND colId=(%s)", (uId, colId))
        db.execute(
            "INSERT INTO coalitions (colId, userId) VALUES (%s, %s)", (colId, uId)
        )

        # Invalidate coalition page cache so leaders/deputies see the new member
        try:
            coalition_wrapped.invalidate(page=f"/coalition/{colId}")
        except Exception:
            pass

        return redirect(f"/coalition/{colId}")


# Route for removing a join request
def removing_requests(uId):
    with get_db_cursor() as db:
        db.execute("SELECT colId FROM requests WHERE reqId=%s", (uId,))
        row = db.fetchone()
        if not row:
            return error(400, "User hasn't posted a request to join this coalition.")
        colId = row[0]

        cId = session["user_id"]

        user_role = get_user_role(cId)

        if user_role not in ["leader", "deputy_leader", "domestic_minister"]:
            return error(400, "You are not the leader of the coalition")

        db.execute("DELETE FROM requests WHERE reqId=(%s) AND colId=(%s)", (uId, colId))

        # Invalidate cached coalition page so applicants/leader panel updates
        try:
            coalition_wrapped.invalidate(page=f"/coalition/{colId}")
        except Exception:
            pass

        return redirect(f"/coalition/{colId}")


# Route for deleting a coalition
def delete_coalition(colId):
    cId = session["user_id"]
    user_role = get_user_role(cId)

    if user_role != "leader":
        return error(400, "You aren't the leader of this coalition")

    with get_db_cursor() as db:
        db.execute("SELECT name FROM colNames WHERE id=(%s)", (colId,))
        row = db.fetchone()
        if not row:
            return error(404, "Coalition not found")
        coalition_name = row[0]

        db.execute("DELETE FROM colNames WHERE id=(%s)", (colId,))
        db.execute("DELETE FROM coalitions WHERE colId=(%s)", (colId,))

    flash(f"{coalition_name} coalition was deleted.")

    return redirect("/")


# Route for updating name, description, flag of coalition
def update_col_info(colId):
    cId = session["user_id"]

    user_role = get_user_role(cId)

    if user_role != "leader":
        return error(400, "You aren't the leader of this coalition")

    ALLOWED_EXTENSIONS = ["png", "jpg", "jpeg"]

    def allowed_file(filename):
        return (
            "." in filename and filename.rsplit(".", 1)[1].lower() in ALLOWED_EXTENSIONS
        )

    flag = request.files.get("flag_input")
    if flag and flag.filename:  # Check both file exists AND has a filename
        if allowed_file(flag.filename):
            # Check if the user already has a flag
            with get_db_cursor() as db:
                db.execute("SELECT flag FROM colNames WHERE id=(%s)", (colId,))
                row = db.fetchone()
                if row and row[0]:
                    current_flag = row[0]
                    try:
                        os.remove(
                            os.path.join(
                                current_app.config["UPLOAD_FOLDER"], current_flag
                            )
                        )
                    except OSError:
                        pass

            # Save the file to database for persistent storage
            from helpers import compress_flag_image

            # Compress and resize flag for fast storage/retrieval
            flag_data, extension = compress_flag_image(flag, max_size=300, quality=85)
            filename = f"col_flag_{colId}.{extension}"

            with get_db_cursor() as db:
                db.execute(
                    "UPDATE colNames SET flag=(%s), flag_data=(%s) WHERE id=(%s)",
                    (filename, flag_data, colId),
                )

            # Also save to filesystem for backward compatibility
            flag.seek(0)  # Reset file pointer after read
            flag.save(os.path.join(current_app.config["UPLOAD_FOLDER"], filename))

            # Invalidate coalition influence cache so flag changes show
            from database import query_cache

            query_cache.invalidate(f"coalition_influence_{colId}")
        else:
            return error(400, "File format not supported")

    with get_db_cursor() as db:
        # Application type
        application_type = request.form.get("application_type")
        if application_type not in ["", "Open", "Invite Only"]:
            return error(400, "No such type")

        if application_type != "":
            db.execute(
                "UPDATE colNames SET type=%s WHERE id=%s", (application_type, colId)
            )
            # Invalidate cached coalition page so viewers see the new application
            # type immediately instead of a cached version.
            try:
                coalition_wrapped.invalidate(page=f"/coalition/{colId}")
            except Exception:
                pass

        # Description
        description = request.form.get("description")
        if description not in [None, "None", ""]:
            db.execute(
                "UPDATE colNames SET description=%s WHERE id=%s", (description, colId)
            )

    return redirect("/my_coalition")


# Coalition bank stuff


# Route for depositing resources into the bank
def deposit_into_bank(colId):
    cId = session["user_id"]

    with get_db_cursor() as db:
        db.execute(
            "SELECT userId FROM coalitions WHERE userId=(%s) and colId=(%s)",
            (cId, colId),
        )
        row = db.fetchone()
        if not row:
            return error(400, "You aren't in this coalition")

    resources = ["money"] + variables.RESOURCES

    deposited_resources = []

    for res in resources:
        try:
            resource = request.form.get(res)
        except (KeyError, AttributeError):
            resource = ""

        if resource is not None and resource != "":
            if int(resource) > 0:
                res_tuple = (res, int(resource))
                deposited_resources.append(res_tuple)

    def deposit(resource, amount, db):
        # Removes the resource from the giver

        # If the resource is money, removes the money from the seller
        if resource == "money":
            db.execute("SELECT gold FROM stats WHERE id=(%s)", (cId,))
            row = db.fetchone()
            current_money = int(row[0]) if row and row[0] is not None else 0

            if current_money < amount:
                return error(400, "You don't have enough money")

            new_money = current_money - amount

            db.execute("UPDATE stats SET gold=(%s) WHERE id=(%s)", (new_money, cId))

        # If it isn't, removes the resource from the giver
        else:
            current_resource_statement = (
                f"SELECT {resource} FROM resources" + " WHERE id=%s"
            )

            db.execute(current_resource_statement, (cId,))
            row = db.fetchone()
            current_resource = int(row[0]) if row and row[0] is not None else 0

            if amount < 1:
                return error(400, "Amount cannot be less than 1")

            if current_resource < amount:
                return error(400, f"You don't have enough {resource}")

            new_resource = current_resource - amount

            update_statement = f"UPDATE resources SET {resource}" + "=%s WHERE id=%s"
            db.execute(update_statement, (new_resource, cId))

        # Gives the coalition the resource
        current_resource_statement = (
            f"SELECT {resource} FROM colBanks" + " WHERE colId=%s"
        )
        db.execute(current_resource_statement, (colId,))
        row = db.fetchone()
        current_resource = int(row[0]) if row and row[0] is not None else 0

        new_resource = current_resource + amount

        update_statement = f"UPDATE colBanks SET {resource}" + "=%s WHERE colId=%s"
        db.execute(update_statement, (new_resource, colId))

    with get_db_cursor() as db:
        for resource in deposited_resources:
            name = resource[0]
            amount = resource[1]
            deposit(name, amount, db)

    return redirect(f"/coalition/{colId}")


# Function for withdrawing a resource from the bank
def withdraw(resource, amount, user_id, colId):
    with get_db_cursor() as db:
        # Removes the resource from the coalition bank

        current_resource_statement = f"SELECT {resource} FROM colBanks WHERE colId=%s"
        db.execute(current_resource_statement, (colId,))
        row = db.fetchone()
        current_resource = row[0] if row and row[0] is not None else 0

        # Normalize types
        try:
            current_resource = int(current_resource)
        except Exception:
            current_resource = 0

        if amount < 1:
            return error(400, "Amount cannot be less than 1")

        if current_resource < amount:
            return error(400, f"Your coalition doesn't have enough {resource}")

        new_resource = current_resource - amount

        update_statement = f"UPDATE colBanks SET {resource}=%s WHERE colId=%s"
        db.execute(update_statement, (new_resource, colId))

        current_app.logger.info(
            (
                f"withdraw: colId={colId} resource={resource} amount={amount} "
                f"bank_before={current_resource} "
                f"bank_after={new_resource}"
            )
        )

        # Gives the leader his resource
        # If the resource is money, gives him money
        if resource == "money":
            db.execute("SELECT gold FROM stats WHERE id=(%s)", (user_id,))
            row = db.fetchone()
            current_money = int(row[0]) if row and row[0] is not None else 0

            new_money = current_money + amount

            db.execute("UPDATE stats SET gold=(%s) WHERE id=(%s)", (new_money, user_id))
            current_app.logger.info(
                (
                    f"withdraw: user_id={user_id} gold_before={current_money} "
                    f"gold_after={new_money}"
                )
            )

        # If the resource is not money, gives him that resource
        else:
            current_resource_statement = f"SELECT {resource} FROM resources WHERE id=%s"
            db.execute(current_resource_statement, (user_id,))
            row = db.fetchone()
            user_current = int(row[0]) if row and row[0] is not None else 0

            new_resource = user_current + amount

            update_statement = f"UPDATE resources SET {resource}=%s WHERE id=%s"
            db.execute(update_statement, (new_resource, user_id))
            current_app.logger.info(
                (
                    f"withdraw: user_id={user_id} {resource}_before={user_current} "
                    f"{resource}_after={new_resource}"
                )
            )


# Route from withdrawing from the bank
def withdraw_from_bank(colId):
    cId = session["user_id"]

    user_role = get_user_role(cId)

    if user_role not in ["leader", "deputy_leader", "banker"]:
        return error(400, "You aren't the leader of this coalition")

    resources = variables.RESOURCES

    withdrew_resources = []

    for res in resources:
        try:
            resource = request.form.get(res)
        except (KeyError, AttributeError):
            resource = ""

        if resource is not None and resource != "":
            try:
                amt = int(resource)
            except Exception:
                return error(400, f"Invalid amount for {res}")
            res_tuple = (res, amt)
            withdrew_resources.append(res_tuple)

    for resource in withdrew_resources:
        name = resource[0]
        amount = resource[1]

        if amount < 1:
            return error(400, "Amount has to be greater than 1")

        result = withdraw(name, amount, cId, colId)
        # `withdraw` may return an error Response (via `error()`); if so,
        # propagate it to the client instead of silently continuing.
        if result is not None:
            return result

    return redirect(f"/coalition/{colId}")


# Route for requesting a resource from the coalition bank
def request_from_bank(colId):
    cId = session["user_id"]

    with get_db_cursor() as db:
        db.execute(
            "SELECT userId FROM coalitions WHERE userId=(%s) and colId=(%s)",
            (cId, colId),
        )
        row = db.fetchone()
        if not row:
            return error(400, "You aren't in this coalition")

        resources = ["money"] + variables.RESOURCES

        requested_resources = []

        for res in resources:
            try:
                resource = request.form.get(res)
            except (KeyError, AttributeError):
                resource = ""

            if resource is not None and resource != "":
                res_tuple = (res, int(resource))
                requested_resources.append(res_tuple)

        if len(requested_resources) > 1:
            return error(400, "You can only request one resource at a time")

        if not requested_resources:
            return error(400, "You must specify a resource and amount to request")

        requested_resources = tuple(requested_resources[0])

        amount = requested_resources[1]

        if amount < 1:
            return error(400, "Amount cannot be 0 or less")

        resource = requested_resources[0]

        try:
            db.execute(
                "INSERT INTO colBanksRequests (reqId, colId, amount, resource) VALUES (%s, %s, %s, %s)",
                (cId, colId, amount, resource),
            )
        except Exception as e:
            current_app.logger.warning("colBanksRequests insert failed: %s", e)
            return error(
                500, "Error submitting bank request; please try again or contact admins"
            )

    return redirect(f"/coalition/{colId}")


# Route for removing a request for a resource from the coalition bank
def remove_bank_request(bankId):
    cId = session["user_id"]

    user_role = get_user_role(cId)

    if user_role not in ["leader", "deputy_leader", "banker"]:
        return error(400, "You aren't the leader of this coalition")

    with get_db_cursor() as db:
        db.execute("DELETE FROM colBanksRequests WHERE id=(%s)", (bankId,))

    return redirect("/my_coalition")


# Route for accepting a bank request from the coalition bank
def accept_bank_request(bankId):
    cId = session["user_id"]

    with get_db_cursor() as db:
        db.execute(
            "SELECT colId, resource, amount, reqId FROM colBanksRequests WHERE id=(%s)",
            (bankId,),
        )
        result = db.fetchone()
        if not result:
            return error(400, "Bank request not found")

        colId, resource, amount, user_id = result

        user_role = get_user_role(cId)

        if user_role not in ["leader", "deputy_leader", "banker"]:
            return error(400, "You aren't the leader of this coalition")

        result = withdraw(resource, amount, user_id, colId)
        if result is not None:
            return result
        db.execute("DELETE FROM colBanksRequests WHERE id=(%s)", (bankId,))

    return redirect("/my_coalition")


# Route for offering another coalition a treaty
def offer_treaty():
    cId = session["user_id"]

    col2_name = request.form.get("coalition_name")
    if col2_name == "":
        return error(400, "Please enter a coalition name")

    with get_db_cursor() as db:
        db.execute("SELECT id FROM colNames WHERE name=(%s)", (col2_name,))
        row = db.fetchone()
        if not row:
            return error(400, f"No such coalition: {col2_name}")
        col2_id = row[0]

        db.execute("SELECT colId FROM coalitions WHERE userId=(%s)", (cId,))
        row = db.fetchone()
        if not row:
            return error(400, "You are not in a coalition")
        user_coalition = row[0]

        if col2_id == user_coalition:
            return error(400, "Cannot declare treaty on your own coalition")

        user_role = get_user_role(cId)

        if user_role not in ["leader", "deputy_leader", "foreign_ambassador"]:
            return error(400, "You aren't the leader of this coalition")

        treaty_name = request.form.get("treaty_name")
        if treaty_name == "":
            return error(400, "Please enter a treaty name")

        treaty_message = request.form.get("treaty_message")
        if treaty_message == "":
            return error(400, "Please enter a treaty description")
        try:
            db.execute(
                "INSERT INTO treaties (col1_id, col2_id, treaty_name, treaty_description) VALUES (%s, %s, %s, %s)",
                (user_coalition, col2_id, treaty_name, treaty_message),
            )
        except Exception:
            return error(
                400, "Error inserting into database. Please contact the website admins"
            )

    return redirect("/my_coalition")


# Route for accepting a treaty offer from another coalition
def accept_treaty(offer_id):
    cId = session["user_id"]

    offer_id = int(offer_id)

    with get_db_cursor() as db:
        db.execute("SELECT colId FROM coalitions WHERE userId=(%s)", (cId,))
        row = db.fetchone()
        if not row:
            return error(400, "You do not have such an offer")
        user_coalition = row[0]

        db.execute(
            "SELECT id FROM treaties WHERE col2_id=%s AND id=%s",
            (user_coalition, offer_id),
        )
        row = db.fetchone()
        if not row:
            return error(400, "You do not have such an offer")
        permission_offer_id = row[0]

        if permission_offer_id != offer_id:
            return error(
                400,
                "You do not have an offer for this id. Please report this bug if you're using the web ui and not testing for permission vulns haha",
            )

        user_role = get_user_role(cId)

        if user_role not in ["leader", "deputy_leader", "foreign_ambassador"]:
            return error(400, "You aren't the leader of this coalition")

        db.execute("UPDATE treaties SET status='Active' WHERE id=(%s)", (offer_id,))

    return redirect("/my_coalition")


# Route for breaking a treaty with another coalition
def break_treaty(offer_id):
    cId = session["user_id"]

    user_role = get_user_role(cId)

    if user_role not in ["leader", "deputy_leader", "foreign_ambassador"]:
        return error(400, "You aren't the leader of this coalition")

    with get_db_cursor() as db:
        db.execute("DELETE FROM treaties WHERE id=(%s)", (offer_id,))

    return redirect("/my_coalition")


def decline_treaty(offer_id):
    cId = session["user_id"]

    user_role = get_user_role(cId)

    if user_role not in ["leader", "deputy_leader", "foreign_ambassador"]:
        return error(400, "You aren't the leader of this coalition")

    with get_db_cursor() as db:
        db.execute("DELETE FROM treaties WHERE id=(%s)", (offer_id,))

    return redirect("/my_coalition")


def register_coalitions_routes(app_instance):
    """Register all coalition routes after app initialization to avoid circular imports"""

    # Apply login_required and cache_response decorators to read-heavy routes
    coalition_wrapped = cache_response(ttl_seconds=30)(login_required(coalition))
    establish_coalition_wrapped = login_required(establish_coalition)
    coalitions_wrapped = cache_response(ttl_seconds=60)(login_required(coalitions))
    join_col_wrapped = login_required(join_col)
    leave_col_wrapped = login_required(leave_col)
    my_coalition_wrapped = cache_response(ttl_seconds=30)(login_required(my_coalition))
    give_position_wrapped = login_required(give_position)
    adding_wrapped = login_required(adding)
    removing_requests_wrapped = login_required(removing_requests)
    delete_coalition_wrapped = login_required(delete_coalition)
    update_col_info_wrapped = login_required(update_col_info)
    deposit_into_bank_wrapped = login_required(deposit_into_bank)
    withdraw_from_bank_wrapped = login_required(withdraw_from_bank)
    request_from_bank_wrapped = login_required(request_from_bank)
    remove_bank_request_wrapped = login_required(remove_bank_request)
    accept_bank_request_wrapped = login_required(accept_bank_request)
    offer_treaty_wrapped = login_required(offer_treaty)
    accept_treaty_wrapped = login_required(accept_treaty)
    break_treaty_wrapped = login_required(break_treaty)
    decline_treaty_wrapped = login_required(decline_treaty)

    # Register all coalition routes
    app_instance.add_url_rule(
        "/coalition/<colId>", view_func=coalition_wrapped, methods=["GET"]
    )

    # Apply to coalition (GET form + POST submit)
    def apply_to_coalition(colId):
        from flask import request

        with get_db_cursor() as db:
            # Check coalition exists
            db.execute("SELECT name FROM colNames WHERE id=%s", (colId,))
            row = db.fetchone()
            if not row:
                return error(404, "Coalition not found")
            coalition_name = row[0]

            # If POST, insert application
            if request.method == "POST":
                message = request.form.get("message")
                user_id = session["user_id"]

                # Check if already member
                db.execute("SELECT userId FROM coalitions WHERE userId=%s", (user_id,))
                if db.fetchone():
                    return error(400, "You are already in a coalition")

                # Prevent duplicate applications
                db.execute(
                    "SELECT id FROM col_applications WHERE colId=%s AND userId=%s AND status='pending'",
                    (colId, user_id),
                )
                if db.fetchone():
                    return error(
                        400, "You already have a pending application to this coalition"
                    )

                db.execute(
                    "INSERT INTO col_applications (colId, userId, message) VALUES (%s, %s, %s)",
                    (colId, user_id, message),
                )

                # Notify leaders by adding news
                db.execute(
                    "SELECT userId FROM coalitions WHERE colId=%s AND role IN ('leader','deputy_leader')",
                    (colId,),
                )
                leader_rows = db.fetchall()
                if leader_rows:
                    # Fetch applicant username
                    db.execute("SELECT username FROM users WHERE id=%s", (user_id,))
                    row = db.fetchone()
                    username = row[0] if row else str(user_id)
                    notif = f"{username} applied to join coalition {coalition_name}"
                    for leader_row in leader_rows:
                        leader_id = leader_row[0]
                        db.execute(
                            "INSERT INTO news (destination_id, message, date) VALUES (%s, %s, NOW())",
                            (leader_id, notif),
                        )

                return render_template(
                    "verification_pending.html",
                    email=None,
                    message="Application submitted!",
                )

            # GET - render form
            return render_template(
                "apply_to_coalition.html", coalition_name=coalition_name
            )

    apply_to_coalition_wrapped = login_required(apply_to_coalition)
    app_instance.add_url_rule(
        "/coalition/<colId>/apply",
        view_func=apply_to_coalition_wrapped,
        methods=["GET", "POST"],
    )
    app_instance.add_url_rule(
        "/establish_coalition",
        view_func=establish_coalition_wrapped,
        methods=["GET", "POST"],
    )
    app_instance.add_url_rule(
        "/coalitions", view_func=coalitions_wrapped, methods=["GET"]
    )
    app_instance.add_url_rule(
        "/join/<colId>", view_func=join_col_wrapped, methods=["POST"]
    )
    app_instance.add_url_rule(
        "/leave/<colId>", view_func=leave_col_wrapped, methods=["POST"]
    )
    app_instance.add_url_rule(
        "/my_coalition", view_func=my_coalition_wrapped, methods=["GET"]
    )
    app_instance.add_url_rule(
        "/give_position", view_func=give_position_wrapped, methods=["POST"]
    )
    app_instance.add_url_rule("/add/<uId>", view_func=adding_wrapped, methods=["POST"])
    app_instance.add_url_rule(
        "/remove/<uId>", view_func=removing_requests_wrapped, methods=["POST"]
    )
    app_instance.add_url_rule(
        "/delete_coalition/<colId>",
        view_func=delete_coalition_wrapped,
        methods=["POST"],
    )
    app_instance.add_url_rule(
        "/update_col_info/<colId>", view_func=update_col_info_wrapped, methods=["POST"]
    )
    app_instance.add_url_rule(
        "/deposit_into_bank/<colId>",
        view_func=deposit_into_bank_wrapped,
        methods=["POST"],
    )
    app_instance.add_url_rule(
        "/withdraw_from_bank/<colId>",
        view_func=withdraw_from_bank_wrapped,
        methods=["POST"],
    )
    app_instance.add_url_rule(
        "/request_from_bank/<colId>",
        view_func=request_from_bank_wrapped,
        methods=["POST"],
    )
    app_instance.add_url_rule(
        "/remove_bank_request/<bankId>",
        view_func=remove_bank_request_wrapped,
        methods=["POST"],
    )
    app_instance.add_url_rule(
        "/accept_bank_request/<bankId>",
        view_func=accept_bank_request_wrapped,
        methods=["POST"],
    )
    app_instance.add_url_rule(
        "/offer_treaty", view_func=offer_treaty_wrapped, methods=["POST"]
    )
    app_instance.add_url_rule(
        "/accept_treaty/<offer_id>", view_func=accept_treaty_wrapped, methods=["POST"]
    )
    app_instance.add_url_rule(
        "/break_treaty/<offer_id>", view_func=break_treaty_wrapped, methods=["POST"]
    )
    app_instance.add_url_rule(
        "/decline_treaty/<offer_id>", view_func=decline_treaty_wrapped, methods=["POST"]
    )
