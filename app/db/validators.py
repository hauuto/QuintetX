from __future__ import annotations

# MongoDB regex constraints
REGEX_MSSV = r"^\d{8}$"
REGEX_USER_ID = r"^(U\d{8}|A\d{4})$"
REGEX_GROUP_ID = r"^T\d{4}[a-zA-Z0-9]{8}$"
REGEX_MATCH_ID = r"^M\d{4}[a-zA-Z0-9]{8}$"
REGEX_GROUP_CODE = r"^GRP-[A-Z0-9]{4}$"
REGEX_NOTIFICATION_ID = r"^N\d{4}[a-zA-Z0-9]{8}$"

USERS_SCHEMA_VALIDATOR = {
    "$jsonSchema": {
        "bsonType": "object",
        "required": [
            "_id",
            "mssv",
            "full_name",
            "password_hash",
            "role",
            "group_id",
            "is_active",
            "created_at",
        ],
        "properties": {
            "_id": {"bsonType": "string", "pattern": REGEX_USER_ID},
            "mssv": {"bsonType": "string", "pattern": REGEX_MSSV},
            "full_name": {"bsonType": "string", "minLength": 1},
            "password_hash": {"bsonType": "string", "minLength": 1},
            "role": {"enum": ["student", "teacher", "admin"]},
            "group_id": {"bsonType": ["string", "null"], "pattern": REGEX_GROUP_ID},
            "class_name": {"bsonType": "string"},
            "username": {"bsonType": "string"},
            "email": {"bsonType": "string"},
            "is_active": {"bsonType": "bool"},
            "created_at": {"bsonType": "date"},
        },
        "additionalProperties": False,
    }
}

GROUPS_SCHEMA_VALIDATOR = {
    "$jsonSchema": {
        "bsonType": "object",
        "required": [
            "_id",
            "group_code",
            "name",
            "description",
            "avatar_url",
            "is_public",
            "leader_id",
            "members",
            "pending_requests",
            "match_history",
            "stats",
            "created_at",
        ],
        "properties": {
            "_id": {"bsonType": "string", "pattern": REGEX_GROUP_ID},
            "group_code": {"bsonType": "string", "pattern": REGEX_GROUP_CODE},
            "name": {"bsonType": "string", "minLength": 1},
            "description": {"bsonType": "string"},
            "avatar_url": {"bsonType": ["string", "null"]},
            "is_public": {"bsonType": "bool"},
            "leader_id": {"bsonType": "string", "pattern": REGEX_USER_ID},
            "members": {
                "bsonType": "array",
                "maxItems": 6,
                "items": {
                    "bsonType": "object",
                    "required": ["user_id", "mssv", "full_name", "joined_at"],
                    "properties": {
                        "user_id": {"bsonType": "string", "pattern": REGEX_USER_ID},
                        "mssv": {"bsonType": "string", "pattern": REGEX_MSSV},
                        "full_name": {"bsonType": "string"},
                        "joined_at": {"bsonType": "date"},
                    },
                    "additionalProperties": False,
                },
            },
            "pending_requests": {
                "bsonType": "array",
                "items": {
                    "bsonType": "object",
                    "required": ["user_id", "mssv", "full_name", "requested_at"],
                    "properties": {
                        "user_id": {"bsonType": "string", "pattern": REGEX_USER_ID},
                        "mssv": {"bsonType": "string", "pattern": REGEX_MSSV},
                        "full_name": {"bsonType": "string"},
                        "requested_at": {"bsonType": "date"},
                    },
                    "additionalProperties": False,
                },
            },
            "match_history": {
                "bsonType": "array",
                "items": {
                    "bsonType": "object",
                    "required": ["match_id", "opponent_group_id", "result", "played_at"],
                    "properties": {
                        "match_id": {"bsonType": "string", "pattern": REGEX_MATCH_ID},
                        "opponent_group_id": {"bsonType": "string", "pattern": REGEX_GROUP_ID},
                        "result": {"enum": ["win", "loss", "draw"]},
                        "played_at": {"bsonType": "date"},
                    },
                    "additionalProperties": False,
                },
            },
            "stats": {
                "bsonType": "object",
                "required": ["total", "wins", "losses", "draws"],
                "properties": {
                    "total": {"bsonType": "int", "minimum": 0},
                    "wins": {"bsonType": "int", "minimum": 0},
                    "losses": {"bsonType": "int", "minimum": 0},
                    "draws": {"bsonType": "int", "minimum": 0},
                },
                "additionalProperties": False,
            },
            "created_at": {"bsonType": "date"},
        },
        "additionalProperties": False,
    }
}

MATCHES_SCHEMA_VALIDATOR = {
    "$jsonSchema": {
        "bsonType": "object",
        "required": [
            "_id",
            "room_name",
            "status",
            "board",
            "teams",
            "current_turn",
            "winner",
            "history",
            "start_time",
            "created_at",
        ],
        "properties": {
            "_id": {"bsonType": "string", "pattern": REGEX_MATCH_ID},
            "room_name": {"bsonType": "string", "minLength": 1},
            "status": {"enum": ["waiting", "playing", "finished"]},
            "rev": {"bsonType": "int", "minimum": 0},
            "updated_at": {"bsonType": ["date", "null"]},
            "mode": {"enum": ["pvp", "pve_greedy", "ai_vs_ai", "player_room"]},
            "created_by": {"bsonType": ["string", "null"]},
            "visibility": {"enum": ["public", "private"]},
            "owner_group_id": {"bsonType": ["string", "null"], "pattern": REGEX_GROUP_ID},
            "opponent_group_id": {"bsonType": ["string", "null"], "pattern": REGEX_GROUP_ID},
            "board": {
                "bsonType": "array",
                "minItems": 40,
                "maxItems": 40,
                "items": {
                    "bsonType": "array",
                    "minItems": 40,
                    "maxItems": 40,
                    "items": {"bsonType": "int", "enum": [0, 1, 2]},
                },
            },
            "teams": {
                "bsonType": "object",
                "required": ["X", "O"],
                "properties": {
                    "X": {
                        "bsonType": "object",
                        "required": ["team_id", "api_key", "is_connected", "last_heartbeat"],
                        "properties": {
                            "team_id": {"bsonType": "string", "pattern": REGEX_GROUP_ID},
                            "api_key": {"bsonType": "string", "minLength": 1},
                            "is_connected": {"bsonType": "bool"},
                            "last_heartbeat": {"bsonType": ["date", "null"]},
                            "kind": {"enum": ["team", "human", "bot"]},
                            "is_bot": {"bsonType": "bool"},
                            "bot": {
                                "bsonType": ["object", "null"],
                                "properties": {
                                    "type": {"enum": ["greedy"]},
                                    "name": {"bsonType": "string"},
                                },
                                "additionalProperties": False,
                            },
                        },
                        "additionalProperties": False,
                    },
                    "O": {
                        "bsonType": "object",
                        "required": ["team_id", "api_key", "is_connected", "last_heartbeat"],
                        "properties": {
                            "team_id": {"bsonType": "string", "pattern": REGEX_GROUP_ID},
                            "api_key": {"bsonType": "string", "minLength": 1},
                            "is_connected": {"bsonType": "bool"},
                            "last_heartbeat": {"bsonType": ["date", "null"]},
                            "kind": {"enum": ["team", "human", "bot"]},
                            "is_bot": {"bsonType": "bool"},
                            "bot": {
                                "bsonType": ["object", "null"],
                                "properties": {
                                    "type": {"enum": ["greedy"]},
                                    "name": {"bsonType": "string"},
                                },
                                "additionalProperties": False,
                            },
                        },
                        "additionalProperties": False,
                    },
                },
                "additionalProperties": False,
            },
            "current_turn": {"enum": ["X", "O"]},
            "winner": {"bsonType": ["string", "null"], "enum": ["X", "O", None]},
            "history": {
                "bsonType": "array",
                "items": {
                    "bsonType": "object",
                    "required": ["x", "y", "p", "t"],
                    "properties": {
                        "x": {"bsonType": "int", "minimum": 0, "maximum": 39},
                        "y": {"bsonType": "int", "minimum": 0, "maximum": 39},
                        "p": {"enum": ["X", "O"]},
                        "t": {"bsonType": "date"},
                    },
                    "additionalProperties": False,
                },
            },
            "events": {
                "bsonType": "array",
                "items": {
                    "bsonType": "object",
                    "required": ["type", "message", "side", "team_id", "payload", "created_at"],
                    "properties": {
                        "type": {"bsonType": "string", "minLength": 1},
                        "message": {"bsonType": "string", "minLength": 1},
                        "side": {"bsonType": ["string", "null"]},
                        "team_id": {"bsonType": ["string", "null"]},
                        "payload": {"bsonType": "object"},
                        "created_at": {"bsonType": "date"},
                    },
                    "additionalProperties": False,
                },
            },
            "start_time": {"bsonType": "date"},
            "started_at": {"bsonType": ["date", "null"]},
            "finished_at": {"bsonType": ["date", "null"]},
            "turn_deadline_at": {"bsonType": ["date", "null"]},
            "finish_reason": {"bsonType": ["string", "null"]},
            "created_at": {"bsonType": "date"},
        },
        "additionalProperties": False,
    }
}

NOTIFICATIONS_SCHEMA_VALIDATOR = {
    "$jsonSchema": {
        "bsonType": "object",
        "required": [
            "_id",
            "user_id",
            "sender_id",
            "type",
            "message",
            "is_read",
            "created_at",
            "status",
            "link",
        ],
        "properties": {
            "_id": {"bsonType": "string", "pattern": REGEX_NOTIFICATION_ID},
            "user_id": {"bsonType": "string", "pattern": REGEX_USER_ID},
            "sender_id": {"bsonType": "string"},
            "type": {
                "enum": [
                    "invite",
                    "join_request",
                    "join_approved",
                    "join_rejected",
                    "invite_accepted",
                    "invite_rejected",
                    "kicked",
                    "info",
                ]
            },
            "message": {"bsonType": "string", "minLength": 1},
            "is_read": {"bsonType": "bool"},
            "status": {"enum": ["pending", "accepted", "rejected", "sent"]},
            "group_id": {"bsonType": ["string", "null"], "pattern": REGEX_GROUP_ID},
            "link": {"bsonType": ["string", "null"]},
            "metadata": {"bsonType": "object"},
            "created_at": {"bsonType": "date"},
        },
        "additionalProperties": False,
    }
}

