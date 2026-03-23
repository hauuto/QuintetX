from datetime import datetime, timedelta

# Mock Database
mock_db = {
    "teams": [
        {
            "id": "TEAM-001",
            "name": "Dragon Slayers",
            "members": [
                {"name": "Nguyen Van A", "mssv": "20201234", "initials": "NA", "role": "Leader"},
                {"name": "Pham Thi Lan", "mssv": "20205678", "initials": "PL", "role": "Member"},
                {"name": "Tran Huy", "mssv": "20209012", "initials": "TH", "role": "Member"}
            ],
            "stats": {"matches": 24, "wins": 18, "losses": 6},
            "api_key": "sk_student_123456789",
            "status": "Active"
        },
        {
            "id": "TEAM-002",
            "name": "Code Warriors",
            "members": [
                {"name": "Le Van B", "mssv": "20204321", "initials": "LB", "role": "Leader"}
            ],
            "stats": {"matches": 20, "wins": 10, "losses": 10},
            "api_key": "sk_student_987654321",
            "status": "Active"
        }
    ],
    "matches": [
        {
            "id": "MATCH-8392",
            "teams": {
                "X": {"team_id": "TEAM-001", "name": "Dragon Slayers", "is_connected": True},
                "O": {"team_id": "TEAM-002", "name": "Code Warriors", "is_connected": False}
            },
            "status": "finished",
            "winner": "X",
            "start_time": (datetime.now() - timedelta(minutes=45)).strftime("%H:%M %d/%m/%Y"),
            "duration": "12:30",
            "move_count": 42
        },
        {
            "id": "MATCH-8341",
            "teams": {
                "X": {"team_id": "TEAM-003", "name": "Beta Squad", "is_connected": False},
                "O": {"team_id": "TEAM-001", "name": "Dragon Slayers", "is_connected": False}
            },
            "status": "finished",
            "winner": "X",
            "start_time": (datetime.now() - timedelta(hours=2)).strftime("%H:%M %d/%m/%Y"),
             "duration": "08:15",
            "move_count": 15
        },
         {
            "id": "MATCH-7201",
            "teams": {
                "X": {"team_id": "TEAM-001", "name": "Dragon Slayers", "is_connected": False},
                "O": {"team_id": "TEAM-004", "name": "Gamma Rays", "is_connected": False}
            },
            "status": "finished",
            "winner": "X",
            "start_time": (datetime.now() - timedelta(days=1)).strftime("%H:%M %d/%m/%Y"),
             "duration": "25:00",
            "move_count": 88
        }
    ],
    "current_match": {
        "id": "MATCH-LIVE-01",
        "room_name": "Phòng thi đấu 01",
        "status": "playing",
        "teams": {
             "X": {"team_id": "TEAM-001", "name": "Dragon Slayers", "is_connected": True, "avatar_color": "bg-[#3547E5]"},
             "O": {"team_id": "TEAM-002", "name": "Code Warriors", "is_connected": False, "avatar_color": "bg-[#E53535]"}
        },
        "time_elapsed": "01:28",
        "turn": "X",
        "history": [
            {"order": 1, "team": "X", "x": 20, "y": 20, "coord": "(20, 20)"},
            {"order": 2, "team": "O", "x": 21, "y": 21, "coord": "(21, 21)"}
        ]
    }
}

