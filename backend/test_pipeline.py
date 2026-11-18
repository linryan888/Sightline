
# =========================================================
# SIGHTLINE PIPELINE ENDPOINT TESTS
# =========================================================
#
# These tests verify the two endpoints added for SIG-75:
#
# 1. GET /chunks/{chunk_id}
#    Retrieves one chunk and its window scoring progress.
#
# 2. GET /pipeline/status
#    Counts how many chunks are in each pipeline status
#    for the authenticated user on a particular date.
#
# We use a fake Supabase client instead of a real database.
# This makes the tests faster, repeatable, and safe to run.
# =========================================================


# SimpleNamespace creates an object with named attributes.
# We use it to imitate a Supabase response with a .data field.
from types import SimpleNamespace

# uuid4 generates random UUIDs for fake users and chunks.
from uuid import uuid4

# TestClient sends simulated HTTP requests to our FastAPI app.
# It does not require a running Uvicorn server.
from fastapi.testclient import TestClient

# Import the actual SightLine FastAPI application.
# We will test the real endpoint functions defined in main.py.
import main


# =========================================================
# FAKE SUPABASE QUERY
# =========================================================
#
# Our actual backend uses Supabase queries like:
#
# supabase.table("chunks") \
#     .select("*") \
#     .eq("id", chunk_id) \
#     .eq("user_id", user_id) \
#     .execute()
#
# FakeQuery imitates this behavior using Python lists.
#
# It supports:
# - select(): choosing records
# - eq(): filtering records by equality
# - execute(): returning the matching records
#
# We only implement the methods needed by our endpoints.
# =========================================================

class FakeQuery:

    def __init__(self, rows):
        # Store the records belonging to this fake table.
        #
        # Example:
        # [
        #     {"id": "123", "status": "uploaded"},
        #     {"id": "456", "status": "split"}
        # ]
        self.rows = rows

        # Store the conditions that records must satisfy.
        #
        # Example:
        # {
        #     "id": "123",
        #     "user_id": "456"
        # }
        #
        # A row must satisfy ALL conditions to be returned.
        self.filters = {}

    def select(self, columns):
        # Real Supabase uses select() to specify columns.
        #
        # Examples:
        # .select("*") retrieves all columns.
        # .select("score") retrieves the score column.
        #
        # Our fake client keeps all columns because our
        # tests only need to verify filtering and counting.
        #
        # Returning self allows method chaining.
        return self

    def eq(self, column, value):
        # eq() means "equals".
        #
        # Example:
        # .eq("status", "split")
        #
        # This means we only want records where:
        # status == "split"
        #
        # Save the condition in our filters dictionary.
        self.filters[column] = value

        # Return the same FakeQuery so additional methods
        # can be chained onto it.
        return self

    def execute(self):
        # Simulate running a database query.
        #
        # For every row, check whether it satisfies
        # every condition in self.filters.
        #
        # row.get(column) retrieves a column's value.
        #
        # all() returns True only when every condition
        # is satisfied.
        matching = [
            row for row in self.rows
            if all(
                row.get(column) == value
                for column, value in self.filters.items()
            )
        ]

        # Real Supabase returns a response object
        # whose .data attribute contains the records.
        #
        # SimpleNamespace lets us imitate that format.
        #
        # Example:
        # result = query.execute()
        # result.data == [{"status": "split"}]
        return SimpleNamespace(data=matching)


# =========================================================
# FAKE SUPABASE CLIENT
# =========================================================
#
# This class represents a small fake database containing:
#
# - A chunks table
# - A windows table
#
# Instead of connecting to Supabase, we store records
# in Python lists.
#
# Every test can create its own fake database with
# exactly the records needed for that scenario.
# =========================================================

class FakeSupabase:

    def __init__(self, chunks, windows):
        # Create a dictionary representing our tables.
        #
        # Each key is a table name.
        # Each value is a list of database records.
        self.tables = {
            "chunks": chunks,
            "windows": windows
        }

    def table(self, name):
        # Return a new query for the requested table.
        #
        # Example:
        # table("chunks") returns the chunk records.
        # table("windows") returns the window records.
        #
        # Creating a new FakeQuery also ensures filters
        # from one query do not affect another query.
        return FakeQuery(self.tables[name])


# =========================================================
# TEST 1: COUNT SCORED WINDOWS
# =========================================================
#
# Endpoint:
# GET /chunks/{chunk_id}
#
# Scenario:
# - One chunk belongs to the authenticated user.
# - The chunk has 60 windows.
# - 48 windows have scores.
# - 12 windows have not been scored.
#
# Expected:
# HTTP 200
# total_windows = 60
# scored_windows = 48
# chunk status = "split"
# =========================================================

def test_chunk_scoring_progress(monkeypatch):

    # Generate unique IDs for our test chunk and user.
    #
    # Supabase uses UUIDs, so we use the same format.
    # str() converts UUID objects into strings.
    chunk_id = str(uuid4())
    user_id = str(uuid4())

    # Create one fake chunk owned by our test user.
    chunks = [
        {
            "id": chunk_id,
            "user_id": user_id,
            "status": "split"
        }
    ]

    # Create 60 windows for this chunk.
    #
    # range(60) generates 0 through 59.
    #
    # For i = 0 through 47:
    # score = 0.5
    #
    # For i = 48 through 59:
    # score = None
    #
    # None represents a NULL database value.
    windows = [
        {
            "chunk_id": chunk_id,
            "score": 0.5 if i < 48 else None
        }
        for i in range(60)
    ]

    # Build a fake Supabase client containing our data.
    fake_supabase = FakeSupabase(chunks, windows)

    # Temporarily replace the real Supabase client.
    #
    # When get_chunk() accesses main.supabase,
    # it will now use our fake database.
    monkeypatch.setattr(main, "supabase", fake_supabase)

    # Override the authentication dependency.
    #
    # Normally FastAPI validates a Bearer token
    # through Supabase Auth.
    #
    # For this test, pretend the current user
    # is our fake user.
    main.app.dependency_overrides[main.get_current_user] = lambda: user_id

    try:
        # Create a test client for the FastAPI application.
        client = TestClient(main.app)

        # Send a simulated GET request.
        response = client.get(f"/chunks/{chunk_id}")

        # HTTP 200 means the request succeeded.
        assert response.status_code == 200

        # Verify all 60 windows were counted.
        assert response.json()["total_windows"] == 60

        # Verify exactly 48 windows were scored.
        assert response.json()["scored_windows"] == 48

        # Verify the chunk's status is unchanged.
        assert response.json()["chunk"]["status"] == "split"

    finally:
        # Remove the fake authentication dependency.
        #
        # This prevents it from affecting later tests.
        # finally runs even if an assertion fails.
        main.app.dependency_overrides.clear()


# =========================================================
# TEST 2: ZERO IS A VALID SCORE
# =========================================================
#
# Endpoint:
# GET /chunks/{chunk_id}
#
# Scenario:
# A chunk contains three windows:
#
# Window 1: score = 0.0
# Window 2: score = 0.8
# Window 3: score = None
#
# Expected:
# total_windows = 3
# scored_windows = 2
#
# Why this matters:
# A score of zero means the ML model assigned a score.
# It does NOT mean the window is unscored.
#
# Only None represents an unscored window.
# =========================================================

def test_zero_score_counts_as_scored(monkeypatch):

    # Create IDs for the chunk and its owner.
    chunk_id = str(uuid4())
    user_id = str(uuid4())

    # Create a chunk belonging to the test user.
    chunks = [
        {
            "id": chunk_id,
            "user_id": user_id,
            "status": "split"
        }
    ]

    # Create three windows with different score values.
    windows = [
        {
            "chunk_id": chunk_id,
            "score": 0.0
        },
        {
            "chunk_id": chunk_id,
            "score": 0.8
        },
        {
            "chunk_id": chunk_id,
            "score": None
        }
    ]

    # Replace Supabase with our fake database.
    monkeypatch.setattr(
        main,
        "supabase",
        FakeSupabase(chunks, windows)
    )

    # Pretend the request comes from the chunk's owner.
    main.app.dependency_overrides[main.get_current_user] = lambda: user_id

    try:
        client = TestClient(main.app)

        # Request the chunk's scoring progress.
        response = client.get(f"/chunks/{chunk_id}")

        # The chunk should be accessible.
        assert response.status_code == 200

        # All three windows should be counted.
        assert response.json()["total_windows"] == 3

        # Both 0.0 and 0.8 count as scored.
        # Only the None value should be excluded.
        assert response.json()["scored_windows"] == 2

    finally:
        # Restore normal authentication behavior.
        main.app.dependency_overrides.clear()


# =========================================================
# TEST 3: NONEXISTENT CHUNK RETURNS 404
# =========================================================
#
# Endpoint:
# GET /chunks/{chunk_id}
#
# Scenario:
# A user requests a chunk ID that does not exist.
#
# Expected:
# HTTP 404 Not Found
#
# Why this matters:
# The API should return a clear error instead of
# crashing or returning an empty success response.
# =========================================================

def test_missing_chunk_returns_404(monkeypatch):

    # Generate an ID for a chunk that will not exist.
    chunk_id = str(uuid4())

    # Generate an ID for our authenticated user.
    user_id = str(uuid4())

    # Both tables are empty.
    #
    # This simulates a database without the requested chunk.
    fake_supabase = FakeSupabase([], [])

    # Replace the real database with the empty fake one.
    monkeypatch.setattr(main, "supabase", fake_supabase)

    # Authenticate as our fake user.
    main.app.dependency_overrides[main.get_current_user] = lambda: user_id

    try:
        client = TestClient(main.app)

        # Request a chunk that does not exist.
        response = client.get(f"/chunks/{chunk_id}")

        # The endpoint should return HTTP 404.
        assert response.status_code == 404

        # Verify the error message matches our endpoint.
        assert response.json()["detail"] == "Chunk not found"

    finally:
        # Clear the authentication override.
        main.app.dependency_overrides.clear()


# =========================================================
# TEST 4: USERS CANNOT ACCESS EACH OTHER'S CHUNKS
# =========================================================
#
# Endpoint:
# GET /chunks/{chunk_id}
#
# Scenario:
# - User A owns a chunk.
# - User B tries to retrieve that chunk.
#
# Expected:
# HTTP 404 Not Found
#
# Why this matters:
# SightLine recordings are private.
#
# The endpoint must filter by both:
# - chunk_id
# - authenticated user_id
#
# Returning 404 also avoids revealing whether
# another user's chunk exists.
# =========================================================

def test_cannot_access_another_users_chunk(monkeypatch):

    # Generate a chunk ID.
    chunk_id = str(uuid4())

    # Generate the actual owner's ID.
    owner_id = str(uuid4())

    # Generate a different user's ID.
    other_user_id = str(uuid4())

    # Create a chunk owned by User A.
    chunks = [
        {
            "id": chunk_id,
            "user_id": owner_id,
            "status": "split"
        }
    ]

    # We don't need window records for this test.
    # The request should fail before querying windows.
    windows = []

    # Replace the real Supabase client.
    monkeypatch.setattr(
        main,
        "supabase",
        FakeSupabase(chunks, windows)
    )

    # Authenticate as User B instead of the owner.
    main.app.dependency_overrides[main.get_current_user] = (
        lambda: other_user_id
    )

    try:
        client = TestClient(main.app)

        # User B requests User A's chunk.
        response = client.get(f"/chunks/{chunk_id}")

        # The API must deny access.
        #
        # Because the chunk does not belong to User B,
        # the query should find no matching records.
        assert response.status_code == 404

        # Confirm the API does not return the chunk data.
        assert response.json()["detail"] == "Chunk not found"

    finally:
        # Restore the original authentication dependency.
        main.app.dependency_overrides.clear()


# =========================================================
# TEST 5: COUNT CHUNKS BY PIPELINE STATUS
# =========================================================
#
# Endpoint:
# GET /pipeline/status?date=YYYY-MM-DD
#
# Scenario:
# Our authenticated user has:
#
# 1 uploaded chunk
# 2 split chunks
# 0 split_failed chunks
# 1 scored chunk
# 1 recap_ready chunk
#
# We also create:
# - A chunk belonging to another user.
# - A chunk belonging to a different date.
#
# Expected:
# Only chunks belonging to the authenticated user
# AND requested date should be counted.
# =========================================================

def test_pipeline_status_counts(monkeypatch):

    # Create the authenticated user's ID.
    user_id = str(uuid4())

    # Create another user's ID.
    other_user_id = str(uuid4())

    # Choose the date we want to query.
    test_date = "2026-11-17"

    # Create fake chunks with different statuses.
    chunks = [

        # One uploaded chunk for our user.
        {
            "user_id": user_id,
            "date": test_date,
            "status": "uploaded"
        },

        # Two split chunks for our user.
        {
            "user_id": user_id,
            "date": test_date,
            "status": "split"
        },
        {
            "user_id": user_id,
            "date": test_date,
            "status": "split"
        },

        # One scored chunk for our user.
        {
            "user_id": user_id,
            "date": test_date,
            "status": "scored"
        },

        # One recap-ready chunk for our user.
        {
            "user_id": user_id,
            "date": test_date,
            "status": "recap_ready"
        },

        # This chunk belongs to another user.
        # It should NOT be included in our counts.
        {
            "user_id": other_user_id,
            "date": test_date,
            "status": "uploaded"
        },

        # This chunk belongs to our user,
        # but it has a different date.
        # It should NOT be included either.
        {
            "user_id": user_id,
            "date": "2026-11-16",
            "status": "split_failed"
        }
    ]

    # No windows are needed for the daily status endpoint.
    windows = []

    # Replace Supabase with our fake data.
    monkeypatch.setattr(
        main,
        "supabase",
        FakeSupabase(chunks, windows)
    )

    # Authenticate as our test user.
    main.app.dependency_overrides[main.get_current_user] = lambda: user_id

    try:
        client = TestClient(main.app)

        # Request pipeline counts for the chosen date.
        response = client.get(
            f"/pipeline/status?date={test_date}"
        )

        # The request should succeed.
        assert response.status_code == 200

        # Confirm the returned date matches our request.
        assert response.json()["date"] == test_date

        # Check the complete counts dictionary.
        #
        # split_failed must be zero because the only
        # split_failed chunk belongs to another date.
        #
        # The other user's uploaded chunk must also
        # be excluded from our uploaded count.
        assert response.json()["counts"] == {
            "uploaded": 1,
            "split": 2,
            "split_failed": 0,
            "scored": 1,
            "recap_ready": 1
        }

    finally:
        # Remove the authentication override.
        main.app.dependency_overrides.clear()


# =========================================================
# TEST 6: AUTHENTICATION IS REQUIRED
# =========================================================
#
# Endpoint:
# GET /pipeline/status
#
# Scenario:
# A client requests pipeline status without a Bearer token.
#
# Expected:
# HTTP 401 Unauthorized
#
# Why this matters:
# Pipeline status contains information about a user's
# private recordings.
#
# Only authenticated users should be able to access it.
# =========================================================

def test_pipeline_requires_authentication():

    # Make sure no fake authentication override remains.
    #
    # This allows the real get_current_user dependency
    # to check for a Bearer token.
    main.app.dependency_overrides.clear()

    # Create a FastAPI test client.
    client = TestClient(main.app)

    # Send a request WITHOUT an Authorization header.
    #
    # We intentionally do not supply:
    # Authorization: Bearer <token>
    response = client.get(
        "/pipeline/status?date=2026-11-17"
    )

    # The authentication dependency should reject
    # the request before accessing the database.
    assert response.status_code == 401

    # Confirm the expected authentication error.
    assert response.json()["detail"] == (
        "Missing authentication token"
    )