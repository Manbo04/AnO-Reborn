from flask import request, render_template, session, redirect, flash, current_app
from helpers import login_required, error
from helpers import get_coalition_influence
import os
from dotenv import load_dotenv

load_dotenv()
import variables
from operator import itemgetter
import datetime
from database import get_db_cursor, cache_response


# Function for getting the coalition role of a user
def get_user_role(user_id):
    with get_db_cursor() as db:
        db.execute("SELECT role FROM coalitions WHERE userId=%s", (user_id,))
        role = db.fetchone()[0]

        return role


# Route for viewing a coalition's page
def coalition(colId):
    with get_db_cursor() as db:
        cId = session["user_id"]

        # OPTIMIZATION: Single query for basic coalition info + member count + total influence
        db.execute(
            """
            SELECT 
                c.name, c.type, c.description, c.flag,
                COUNT(DISTINCT coal.userId) AS members_count,
                COALESCE(SUM((SELECT COALESCE(SUM(population), 0) FROM provinces WHERE userId = coal.userId)), 0) AS total_influence
            FROM colNames c
            LEFT JOIN coalitions coal ON c.id = coal.colId
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

        try:
            db.execute(
                "SELECT coalitions.userId, users.username FROM coalitions INNER JOIN users ON coalitions.userId=users.id WHERE coalitions.role='leader' AND coalitions.colId=%s",
                (colId,),
            )
            leaders = db.fetchall()
        except (TypeError, AttributeError, IndexError):
            leaders = []

        try:
            # stats table has no influence column; keep list lightweight and avoid bad column reference
            db.execute(
                """
                SELECT coalitions.userId,
                       users.username,
                       coalitions.role,
                       0 AS influence,
                       (SELECT COUNT(*) FROM provinces WHERE userId = coalitions.userId) AS province_count
                FROM coalitions
                INNER JOIN users ON coalitions.userId = users.id
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
            user_role = get_user_role(cId)
        except (TypeError, AttributeError, IndexError):
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
                except (TypeError, Exception):
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
            except (TypeError, Exception):
                ingoing_treaties = {}
                ingoing_length = 0

            #### ACTIVE ####
            try:
                try:
                    db.execute(
                        "SELECT id FROM treaties WHERE col2_id=(%s) AND status='Active' OR col1_id=(%s) ORDER BY id ASC",
                        (colId, colId),
                    )
                    raw_active_ids = db.fetchall()
                except (TypeError, Exception):
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
            except (TypeError, Exception):
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

        if user_role == "leader" and colType != "Open" and userInCurCol:
            db.execute(
                "SELECT message FROM requests WHERE colId=(%s) ORDER BY reqId ASC",
                (colId,),
            )
            requestMessages = db.fetchall()
            db.execute(
                "SELECT reqId FROM requests WHERE colId=(%s) ORDER BY reqId ASC",
                (colId,),
            )
            # Use JOIN query to fetch request IDs and names together
            db.execute(
                """SELECT r.reqId, u.username, r.message
                   FROM requests r
                   INNER JOIN users u ON r.reqId = u.id
                   WHERE r.colId=%s""",
                (colId,),
            )
            request_data = db.fetchall()

            requestIds = [(r[0],) for r in request_data]
            requestNames = [r[1] for r in request_data]
            requestMessages = [r[2] for r in request_data]

            requests = zip(requestIds, requestNames, requestMessages)
        else:
            requests = []
            requestIds = []

        ### BANK STUFF
        if user_role == "leader" and userInCurCol:
            # Use JOIN query to fetch bank requests with usernames
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

        return render_template(
            "coalition.html",
            name=name,
            colId=colId,
            user_role=user_role,
            description=description,
            colType=colType,
            userInCol=userInCol,
            requests=requests,
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
                db.execute(
                    "INSERT INTO colNames (name, type, description, date) VALUES (%s, %s, %s, %s)",
                    (name, cType, desc, date),
                )

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
    """Coalition rankings page - optimized single query"""
    with get_db_cursor() as db:
        search = request.values.get("search")
        sort = request.values.get("sort")
        sortway = request.values.get("sortway")

        # Single optimized query: get all coalition data with pre-calculated influence
        # This replaces N+1 queries (one per coalition) with a single query
        db.execute(
            """
            SELECT 
                c.id,
                c.type,
                c.name,
                c.flag,
                COUNT(DISTINCT coal.userId) AS members,
                c.date,
                COALESCE(SUM(
                    (SELECT COALESCE(SUM(population), 0) FROM provinces WHERE userId = coal.userId)
                ), 0) AS total_influence
            FROM colNames c
            INNER JOIN coalitions coal ON c.id = coal.colId
            GROUP BY c.id, c.type, c.name, c.flag, c.date
            """
        )
        coalitionsDb = db.fetchall()

        coalitions_list = []
        for row in coalitionsDb:
            col_id, col_type, name, flag, members, col_date, influence = row
            
            # Apply search filter
            if search and search.lower() not in name.lower():
                continue
                
            # Apply type filter
            if sort == "invite_only" and col_type == "Open":
                continue
            if sort == "open" and col_type == "Invite Only":
                continue

            # Calculate unix timestamp for age sorting
            try:
                date_obj = datetime.datetime.fromisoformat(str(col_date))
                unix = int((date_obj - datetime.datetime(1970, 1, 1)).total_seconds())
            except (ValueError, TypeError):
                unix = 0

            coalitions_list.append({
                'id': col_id,
                'type': col_type,
                'name': name,
                'flag': flag,
                'members': members,
                'date': col_date,
                'influence': influence,
                'unix': unix
            })

        # Default sorting
        if not sort or sort in ["open", "invite_only"]:
            sort = "influence"
            if not sortway:
                sortway = "desc"

        reverse = sortway == "desc"

        # Sort the results
        if sort == "influence":
            coalitions_list.sort(key=lambda x: x['influence'], reverse=reverse)
        elif sort == "members":
            coalitions_list.sort(key=lambda x: x['members'], reverse=reverse)
        elif sort == "age":
            coalitions_list.sort(key=lambda x: x['unix'], reverse=not reverse)

        return render_template("coalitions.html", coalitions=coalitions_list)


# Route for joining a coalition
def join_col(colId):
    with get_db_cursor() as db:
        cId = session["user_id"]

        try:
            db.execute("SELECT colId FROM coalitions WHERE userId=%s", (cId,))
            db.fetchone()[0]

            return error(400, "You're already in a coalition")
        except (TypeError, AttributeError):
            pass

        db.execute("SELECT type FROM colNames WHERE id=%s", (colId,))
        colType = db.fetchone()[0]

        if colType == "Open":
            db.execute(
                "INSERT INTO coalitions (colId, userId) VALUES (%s, %s)", (colId, cId)
            )
        else:
            db.execute(
                "SELECT FROM requests WHERE colId=%s and reqId=%s",
                (
                    colId,
                    cId,
                ),
            )
            duplicate = db.fetchone()
            if duplicate is not None:
                return error(
                    400, "You've already submitted a request to join this coalition"
                )

            message = request.form["message"]
            db.execute(
                "INSERT INTO requests (colId, reqId, message) VALUES (%s, %s, %s)",
                (colId, cId, message),
            )

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

        try:
            db.execute("SELECT colId FROM coalitions WHERE userId=%s", (cId,))
            coalition = db.fetchone()[0]
        except TypeError:
            return redirect("/")  # Redirects to home page instead of an error

    return redirect(f"/coalition/{coalition}")


# Route for giving someone a role in your coalition
def give_position():
    with get_db_cursor() as db:
        cId = session["user_id"]

        try:
            db.execute("SELECT colId FROM coalitions WHERE userId=%s", (cId,))
            colId = db.fetchone()[0]
        except (TypeError, AttributeError):
            return error(400, "You are not a part of any coalition")

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
                "SELECT users.id, coalitions.colid, coalitions.role FROM users INNER JOIN coalitions ON users.id=coalitions.userid WHERE users.username=%s",
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

        db.execute("UPDATE coalitions SET role=%s WHERE userId=%s", (role, roleer))

        return redirect("/my_coalition")


# Route for accepting a coalition join request
def adding(uId):
    with get_db_cursor() as db:
        try:
            db.execute("SELECT colId FROM requests WHERE reqId=(%s)", (uId,))
            colId = db.fetchone()[0]
        except TypeError:
            return error(400, "User hasn't posted a request to join")

        cId = session["user_id"]
        user_role = get_user_role(cId)

        if user_role not in ["leader", "deputy_leader", "domestic_minister"]:
            return error(400, "You are not a leader of the coalition")

        db.execute("DELETE FROM requests WHERE reqId=(%s) AND colId=(%s)", (uId, colId))
        db.execute(
            "INSERT INTO coalitions (colId, userId) VALUES (%s, %s)", (colId, uId)
        )

        return redirect(f"/coalition/{colId}")


# Route for removing a join request
def removing_requests(uId):
    with get_db_cursor() as db:
        try:
            db.execute("SELECT colId FROM requests WHERE reqId=%s", (uId,))
            colId = db.fetchone()[0]
        except TypeError:
            return error(400, "User hasn't posted a request to join this coalition.")

        cId = session["user_id"]

        user_role = get_user_role(cId)

        if user_role not in ["leader", "deputy_leader", "domestic_minister"]:
            return error(400, "You are not the leader of the coalition")

        db.execute("DELETE FROM requests WHERE reqId=(%s) AND colId=(%s)", (uId, colId))

        return redirect(f"/coalition/{colId}")


# Route for deleting a coalition
def delete_coalition(colId):
    cId = session["user_id"]
    user_role = get_user_role(cId)

    if user_role != "leader":
        return error(400, "You aren't the leader of this coalition")

    with get_db_cursor() as db:
        db.execute("SELECT name FROM colNames WHERE id=(%s)", (colId,))
        coalition_name = db.fetchone()[0]

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
                try:
                    db.execute("SELECT flag FROM colNames WHERE id=(%s)", (colId,))
                    current_flag = db.fetchone()[0]

                    # If he does, delete the flag
                    os.remove(
                        os.path.join(current_app.config["UPLOAD_FOLDER"], current_flag)
                    )

                except (OSError, FileNotFoundError, TypeError):
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

        # Description
        description = request.form.get("description")
        if description not in [None, "None", ""]:
            db.execute(
                "UPDATE colNames SET description=%s WHERE id=%s", (description, colId)
            )

    return redirect("/my_coalition")


### COALITION BANK STUFF ###


# Route for depositing resources into the bank
def deposit_into_bank(colId):
    cId = session["user_id"]

    try:
        with get_db_cursor() as db:
            db.execute(
                "SELECT userId FROM coalitions WHERE userId=(%s) and colId=(%s)",
                (cId, colId),
            )
            db.fetchone()[0]
    except TypeError:
        return redirect(400, "You aren't in this coalition")

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
            current_money = int(db.fetchone()[0])

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
            current_resource = int(db.fetchone()[0])

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
        current_resource = int(db.fetchone()[0])

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
            f"withdraw: colId={colId} resource={resource} amount={amount} bank_before={current_resource} bank_after={new_resource}"
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
                f"withdraw: user_id={user_id} gold_before={current_money} gold_after={new_money}"
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
                f"withdraw: user_id={user_id} {resource}_before={user_current} {resource}_after={new_resource}"
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
        try:
            db.execute(
                "SELECT userId FROM coalitions WHERE userId=(%s) and colId=(%s)",
                (cId, colId),
            )
            db.fetchone()[0]
        except TypeError:
            return redirect(400, "You aren't in this coalition")

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

        requested_resources = tuple(requested_resources[0])

        amount = requested_resources[1]

        if amount < 1:
            return error(400, "Amount cannot be 0 or less")

        resource = requested_resources[0]

        db.execute(
            "INSERT INTO colBanksRequests (reqId, colId, amount, resource) VALUES (%s, %s, %s, %s)",
            (cId, colId, amount, resource),
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
        try:
            db.execute("SELECT id FROM colNames WHERE name=(%s)", (col2_name,))
            col2_id = db.fetchone()[0]
        except (TypeError, AttributeError):
            return error(400, f"No such coalition: {col2_name}")

        try:
            db.execute("SELECT colId FROM coalitions WHERE userId=(%s)", (cId,))
            user_coalition = db.fetchone()[0]
        except (TypeError, AttributeError):
            return error(400, "You are not in a coalition")

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
        try:
            db.execute("SELECT colId FROM coalitions WHERE userId=(%s)", (cId,))
            user_coalition = db.fetchone()[0]

            db.execute(
                "SELECT id FROM treaties WHERE col2_id=%s AND id=%s",
                (user_coalition, offer_id),
            )
            permission_offer_id = db.fetchone()[0]

        except (TypeError, AttributeError):
            return error(400, "You do not have such an offer")

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
