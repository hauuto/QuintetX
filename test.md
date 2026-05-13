# QuintetX Test Plan

## 1. Mục tiêu kiểm thử

Tài liệu này mô tả các testcase Manual + API cho toàn bộ chức năng QuintetX dựa trên `system.md`.

Phạm vi test:

- Auth student/admin.
- API authentication/authorization.
- Team/group management.
- Notifications.
- Match management.
- Agent/SDK protocol.
- Game engine Gomoku.
- Greedy Bot.
- Student UI flows.
- Admin UI flows.
- System/health/metrics/download.
- Negative/edge cases.

## 2. Môi trường test đề xuất

| Thành phần | Giá trị |
|---|---|
| App | FastAPI/Uvicorn |
| Server | `http://localhost:2111` |
| DB | MongoDB local |
| Database | `quintetx` |
| Board size | 40x40 |
| Move timeout | 10s |
| Test mode | `APP_ENV=dev` |

## 3. Dữ liệu seed mặc định

| Loại | Giá trị |
|---|---|
| Admin username | `admin` |
| Admin password | `admin` |
| Admin ID | `A0001` |
| Student 1 | MSSV `23012345`, password `SeedPass123` |
| Student 2 | MSSV `23012346`, password `SeedPass123` |
| Student 3 | MSSV `23012347`, password `SeedPass123` |
| Team Alpha | `T0001padjsl92`, code `GRP-A3F9` |
| Team Beta | `T0002p24jslp2`, code `GRP-B7K2` |

## 4. Quy ước testcase

| Cột | Ý nghĩa |
|---|---|
| ID | Mã testcase |
| Type | Manual, API, Manual+API |
| Priority | P0 critical, P1 high, P2 medium |
| Preconditions | Điều kiện trước khi test |
| Steps | Bước thực hiện |
| Expected result | Kết quả mong đợi |

## 5. Ma trận quyền

| Chức năng | Guest | Student | Leader | Admin | Agent |
|---|---:|---:|---:|---:|---:|
| Register student | Yes | No need | No need | No need | No |
| Login student | Yes | Yes | Yes | No | No |
| Login admin | Yes | No | No | Yes | No |
| Create group | No | Yes nếu chưa có group | No nếu đã có group | No | No |
| Join group | No | Yes nếu chưa có group | No nếu đã có group | No | No |
| Approve join | No | No | Yes | No | No |
| Invite member | No | No | Yes | No | No |
| Create team-vs-team match | No | No | No | Yes | No |
| Create bot match | No | Yes nếu có group | Yes | No | No |
| Agent init/state/move | No | No | No | No | Yes |
| Admin dashboard | No | No | No | Yes | No |

## 6. Auth testcase

| ID | Type | Priority | Preconditions | Steps | Expected result |
|---|---|---|---|---|---|
| AUTH-001 | Manual+API | P0 | App running | Open `/register`; submit valid MSSV 8 digits, name, class, password, confirm password | Account created; API returns `status=success`; user ID `U{mssv}` |
| AUTH-002 | API | P0 | None | `POST /api/v1/auth/register/student` with MSSV length != 8 | `status=error` or 422; user not created |
| AUTH-003 | API | P0 | None | Register with non-digit MSSV 8 chars | Error message `MSSV must be exactly 8 digits` |
| AUTH-004 | API | P0 | Existing MSSV | Register same MSSV again | `status=error`; message duplicate MSSV |
| AUTH-005 | API | P0 | None | Register with password != confirm_password | `status=error`; no user inserted |
| AUTH-006 | Manual+API | P0 | Existing student | Login via `/login` or `POST /api/v1/auth/login/student` | Returns JWT, token_type `bearer`, user role `student` |
| AUTH-007 | API | P0 | Existing student | Login with wrong password | `status=error`; no access token |
| AUTH-008 | API | P0 | Existing student | Login with invalid MSSV format | `status=error` or 422 |
| AUTH-009 | Manual+API | P0 | Seed admin exists | Login admin via `/admin/login` or `POST /api/v1/auth/login/admin` | Returns JWT, user role `admin` |
| AUTH-010 | API | P0 | Seed admin exists | Admin login wrong password | `status=error`; no access token |
| AUTH-011 | API | P0 | Valid JWT | Call protected endpoint with `Authorization: Bearer <token>` | Request succeeds |
| AUTH-012 | API | P0 | None | Call protected endpoint without Authorization | HTTP 401 JSON error |
| AUTH-013 | API | P0 | None | Call protected endpoint with malformed Bearer token | HTTP 401 JSON error |
| AUTH-014 | API | P1 | Expired/invalid JWT | Call protected endpoint | HTTP 401 `Invalid or expired token` |

## 7. Group/team testcase

| ID | Type | Priority | Preconditions | Steps | Expected result |
|---|---|---|---|---|---|
| TEAM-001 | Manual+API | P0 | Student logged in, no group | `POST /api/v1/groups` with valid name/description | Group created; user `group_id` set; creator in members; creator is leader |
| TEAM-002 | API | P0 | Student already has group | `POST /api/v1/groups` again | `status=error`; message user already has group |
| TEAM-003 | API | P1 | Student logged in | `GET /api/v1/groups/me` | Returns current group or `group=null` |
| TEAM-004 | API | P1 | Student logged in | `GET /api/v1/groups/me/dashboard` | Returns team, stats, recent matches |
| TEAM-005 | Manual+API | P1 | Public group exists with < 6 members | `GET /api/v1/groups/open-missing` | Returns list with slots_left > 0 |
| TEAM-006 | API | P1 | Public groups exist | Call open groups with search query `q` | Result filtered by name |
| TEAM-007 | API | P1 | Many groups exist | Call open groups with page/page_size | Pagination fields correct |
| TEAM-008 | Manual+API | P0 | Student without group, public group exists | `POST /api/v1/groups/{group_id}/join` | Pending request appended; leader receives notification |
| TEAM-009 | API | P0 | Student already has group | Request join another group | `status=error`; no pending request |
| TEAM-010 | API | P0 | Private group exists | Student requests join private group | `status=error`; private group rejects direct join |
| TEAM-011 | API | P0 | Group has 6 members | Student requests join full group | `status=error`; group full |
| TEAM-012 | API | P1 | Join request already exists | Same student sends join request again | `status=error`; no duplicate request |
| TEAM-013 | Manual+API | P0 | Leader logged in, pending request exists | `GET /groups/{group_id}/join-requests` | Pending requests returned |
| TEAM-014 | API | P0 | Non-leader logged in | Get join requests | 403 or error; only leader allowed |
| TEAM-015 | Manual+API | P0 | Leader logged in, pending request exists | Approve request | User added to members; user.group_id set; pending removed; notification sent |
| TEAM-016 | API | P0 | Leader logged in, group full | Approve request | `status=error`; no member added |
| TEAM-017 | API | P1 | Leader logged in, pending request exists | Reject request | Pending removed; notification sent; user.group_id unchanged |
| TEAM-018 | Manual+API | P0 | Leader logged in, target student no group | Invite by MSSV | Invite notification created for target user |
| TEAM-019 | API | P0 | Leader logged in | Invite non-existing MSSV | `status=error`; user not found |
| TEAM-020 | API | P0 | Leader logged in | Invite self | `status=error`; cannot invite yourself |
| TEAM-021 | API | P0 | Target already has group | Invite target | `status=error`; user already has group |
| TEAM-022 | Manual+API | P0 | Target user has pending invite | Accept invite | User added to group; user.group_id set; invite status accepted/read; leader notified |
| TEAM-023 | Manual+API | P1 | Target user has pending invite | Reject invite | Invite status rejected/read; leader notified; user.group_id unchanged |
| TEAM-024 | API | P0 | Current user has no matching invite | Accept unknown invite ID | `status=error`; invite not found |
| TEAM-025 | Manual+API | P1 | Leader logged in | Rename group | Group name updated |
| TEAM-026 | API | P0 | Non-leader logged in | Rename group | 403 or error |
| TEAM-027 | Manual+API | P1 | Leader logged in, group has member | Kick member | Member removed; kicked user.group_id null; notification sent |
| TEAM-028 | API | P0 | Leader logged in | Leader attempts kick self | `status=error`; leader not removed |
| TEAM-029 | API | P1 | Student logged in | Search player by valid MSSV | Returns player summary and has_group flag |
| TEAM-030 | API | P1 | Student logged in | Search player by missing MSSV | Returns `player=null` |

## 8. Notification testcase

| ID | Type | Priority | Preconditions | Steps | Expected result |
|---|---|---|---|---|---|
| NOTIF-001 | Manual+API | P1 | User has notifications | `GET /api/v1/groups/notifications/me` | Returns notifications sorted newest first |
| NOTIF-002 | API | P1 | User has read/unread notifications | `GET /notifications/me?unread_only=true` | Only unread notifications returned |
| NOTIF-003 | API | P1 | User has unread notifications | `PATCH /notifications/read-all` | All user notifications marked read |
| NOTIF-004 | API | P1 | User has notification | `PATCH /notifications/{id}/read` | That notification marked read |
| NOTIF-005 | API | P1 | Notification belongs to another user | Current user marks it read | HTTP 404 or not found |
| NOTIF-006 | Manual | P2 | Browser logged in | Open student team page after invite/join updates | Notification shown with sender_name/link |

## 9. Match management testcase

| ID | Type | Priority | Preconditions | Steps | Expected result |
|---|---|---|---|---|---|
| MATCH-001 | API | P0 | Admin logged in, two teams exist | `GET /api/v1/matches/teams/options` | Returns teams list |
| MATCH-002 | API | P0 | Student logged in | Call `/matches/teams/options` | `status=error`; only admin |
| MATCH-003 | Manual+API | P0 | Admin logged in, two teams with no active match | `POST /api/v1/matches` valid payload | Match created waiting; board hidden in response; API keys returned for X/O |
| MATCH-004 | API | P0 | Admin logged in | Create match with same X/O team | `status=error`; teams must differ |
| MATCH-005 | API | P0 | Admin logged in | Create match with missing/non-existing team ID | `status=error`; team does not exist |
| MATCH-006 | API | P0 | Team already has waiting/playing match | Create another match using same team | `status=error`; active conflict |
| MATCH-007 | API | P0 | Student logged in | Student calls create team-vs-team match | `status=error`; only admin |
| MATCH-008 | API | P1 | Admin logged in | Create match with invalid start_time | `status=error`; invalid ISO datetime |
| MATCH-009 | Manual+API | P0 | Student with group, no active match | `POST /api/v1/matches/bot` | Match created waiting; my_team side X; API key returned; bot side connected |
| MATCH-010 | API | P0 | Student without group | Create bot match | `status=error`; require group |
| MATCH-011 | API | P0 | Student group has active match | Create bot match again | `status=error`; active conflict |
| MATCH-012 | API | P0 | Admin logged in | Admin calls create bot match | `status=error`; only student |
| MATCH-013 | API | P1 | Authenticated user | `GET /api/v1/matches/overview` | Returns current/upcoming/finished arrays |
| MATCH-014 | Manual+API | P1 | Student with active match | `GET /api/v1/matches/me` | Returns `my_current_match`, `my_team.id/side/api_key` |
| MATCH-015 | API | P1 | Student without group | `GET /matches/me` | `my_current_match=null`, `my_team=null`, other_matches returned |
| MATCH-016 | API | P1 | Student with active match | `GET /matches/me/summary?since_rev=<same>` | `rev_changed=false` |
| MATCH-017 | API | P1 | Match rev changes | `GET /matches/me/summary?since_rev=<old>` | `rev_changed=true` |
| MATCH-018 | API | P1 | Match exists | `GET /matches/{match_id}/events` | Returns latest events |
| MATCH-019 | API | P1 | Match has > limit events | Call events with `limit=10` | Returns max 10 latest events |
| MATCH-020 | API | P1 | Student has finished matches | `GET /matches/my/history` | Returns finished matches with my_side/move_count/result fields |
| MATCH-021 | API | P1 | Student without group | `GET /matches/my/history` | Returns empty list |
| MATCH-022 | API | P1 | Match exists | `GET /matches/{match_id}` | Returns match with board/history/events; no API keys leaked |
| MATCH-023 | API | P0 | Admin logged in, match exists | `DELETE /matches/{match_id}` | Match deleted; deleted_match_id returned |
| MATCH-024 | API | P0 | Student logged in, match exists | Delete match | `status=error`; only admin |
| MATCH-025 | API | P1 | Admin logged in | Delete unknown match ID | `status=error`; match not found |

## 10. Agent/SDK protocol testcase

| ID | Type | Priority | Preconditions | Steps | Expected result |
|---|---|---|---|---|---|
| AGENT-001 | API | P0 | Waiting match exists, valid X creds | `POST /api/v1/agent/init` with X headers | X marked connected; event `agent_ready`; response state returned |
| AGENT-002 | API | P0 | Waiting match exists, valid X/O creds | Init both X and O | Match status becomes `playing`; current_turn `X`; event `match_started`; deadline set |
| AGENT-003 | API | P0 | Missing agent headers | Call `/agent/init` | HTTP 401 missing credentials |
| AGENT-004 | API | P0 | Invalid API key | Call `/agent/init` | HTTP 401 invalid agent credentials |
| AGENT-005 | API | P1 | Playing match, valid creds | `GET /api/v1/agent/state` | Returns board, turn, side, match_status, teams, events |
| AGENT-006 | API | P1 | Playing match, valid creds | `POST /api/v1/agent/heartbeat` | Updates side heartbeat; returns side and timestamp |
| AGENT-007 | API | P0 | Playing match, X turn | X posts valid move `{x:0,y:0}` | Board[0][0]=1; history appended; rev increments; turn changes to O |
| AGENT-008 | API | P0 | Playing match, O turn | X posts move | `status=error`; message not your turn; move_rejected event |
| AGENT-009 | API | P0 | Playing match | Post move outside board `{x:40,y:0}` | `status=error`; out of board range |
| AGENT-010 | API | P0 | Cell already occupied | Other side posts same cell | `status=error`; cell occupied/state changed |
| AGENT-011 | API | P0 | Match waiting, only one side connected | Side posts move | `status=error`; match is not playing |
| AGENT-012 | API | P0 | Match finished | Side posts move | `status=error`; match is not playing |
| AGENT-013 | API | P1 | Playing match | Several valid alternating moves | Board/history/events/rev consistent after each move |
| AGENT-014 | Manual+API | P1 | SDK files available | Run SDK against active match | SDK connects, heartbeat starts, state polling works, move submitted on turn |
| AGENT-015 | Manual+API | P1 | Invalid local solution returns invalid move | Run SDK/strategy invalid output | Server rejects or bot fallback applies where relevant; app remains stable |

## 11. Game engine testcase

| ID | Type | Priority | Preconditions | Steps | Expected result |
|---|---|---|---|---|---|
| GAME-001 | API | P0 | Playing match | X creates 5 horizontal cells via alternating legal moves | Match finished; winner X; finish_reason `win`; win events present |
| GAME-002 | API | P0 | Playing match | X creates 5 vertical cells | Match finished; winner X |
| GAME-003 | API | P0 | Playing match | X creates 5 diagonal down-right cells | Match finished; winner X |
| GAME-004 | API | P0 | Playing match | X creates 5 diagonal up-right cells | Match finished; winner X |
| GAME-005 | API | P1 | Playing match | Create only 4 consecutive cells | Match remains playing; no winner |
| GAME-006 | API | P1 | Playing match | Create 5 with a gap | No win detected |
| GAME-007 | API | P0 | Playing match, deadline expired | Trigger `/agent/state` or `/agent/move` after > timeout | Current turn side loses; winner other side; finish_reason `timeout_forfeit` |
| GAME-008 | API | P1 | Board nearly full no winning moves | Last empty move fills board | Draw or terminal full-board behavior handled without crash |
| GAME-009 | API | P1 | Playing match | Verify board encoding after X/O moves | X stored as 1, O stored as 2, empty remains 0 |
| GAME-010 | API | P1 | Playing match | Verify current_turn flips after valid non-winning move | X -> O -> X |

## 12. Greedy Bot testcase

| ID | Type | Priority | Preconditions | Steps | Expected result |
|---|---|---|---|---|---|
| BOT-001 | Manual+API | P0 | Student with group, no active match | Create bot match; init student agent | Match starts because bot is connected; student is X |
| BOT-002 | API | P0 | Bot match playing, after X valid move | Server triggers bot turn | Bot places O move; board updated; turn returns to X unless bot wins |
| BOT-003 | API | P1 | Bot strategy returns invalid move or raises | Trigger bot turn | Server uses first empty fallback; no crash |
| BOT-004 | API | P1 | Bot can make winning move | Trigger bot turn | Match finished; winner O; finish_reason `win` |
| BOT-005 | API | P1 | Full board before bot move | Trigger bot turn | Match finishes draw; no crash |

## 13. Student UI testcase

| ID | Type | Priority | Preconditions | Steps | Expected result |
|---|---|---|---|---|---|
| UI-STU-001 | Manual | P0 | App running | Open `/` | Student login page rendered |
| UI-STU-002 | Manual | P0 | App running | Open `/login` | Student login page rendered |
| UI-STU-003 | Manual | P0 | App running | Open `/register` | Register page rendered |
| UI-STU-004 | Manual | P0 | Valid student | Login via UI | Redirect/dashboard works; token stored; protected calls succeed |
| UI-STU-005 | Manual | P1 | Student logged in | Open `/student/dashboard` | Dashboard page renders group stats/recent matches |
| UI-STU-006 | Manual | P1 | Student logged in | Open `/student/team` | Team page renders current team or join/create UI |
| UI-STU-007 | Manual | P1 | Student without group | Create group from UI | Team appears after success |
| UI-STU-008 | Manual | P1 | Student without group | Search/open groups; send join request | UI shows request sent; leader notification exists |
| UI-STU-009 | Manual | P1 | Target has invite | Accept invite from UI | User joins group; UI updates |
| UI-STU-010 | Manual | P1 | Student with active match | Open `/student/match` | Board/status/my API key/events render |
| UI-STU-011 | Manual | P1 | Active match changing | Keep match page open during moves | UI updates via polling/rev |
| UI-STU-012 | Manual | P1 | Student has finished matches | Open `/student/history` | Match history renders |
| UI-STU-013 | Manual | P1 | App running | Open `/student/instructions` | Instructions page renders |
| UI-STU-014 | Manual | P1 | Unauthenticated browser | Call API via page or direct protected route behavior | 401 page/redirect works for API client |

## 14. Admin UI testcase

| ID | Type | Priority | Preconditions | Steps | Expected result |
|---|---|---|---|---|---|
| UI-ADM-001 | Manual | P0 | App running | Open `/admin/login` | Admin login page rendered |
| UI-ADM-002 | Manual | P0 | Valid admin | Login via admin UI | Admin token stored; admin pages usable |
| UI-ADM-003 | Manual | P1 | Admin logged in | Open `/admin/dashboard` | Counts teams/matches/rooms render |
| UI-ADM-004 | Manual | P1 | Admin logged in | Open `/admin/teams` | Teams list renders with name/member count/status/date |
| UI-ADM-005 | Manual | P1 | Admin logged in | Open `/admin/rooms` | Rooms list renders with team names/status |
| UI-ADM-006 | Manual+API | P0 | Admin logged in, teams exist | Open `/admin/match`; create match | Match created; API keys shown/available |
| UI-ADM-007 | Manual+API | P1 | Admin logged in, match exists | Delete match from admin flow/API | Match removed from rooms/overview |
| UI-ADM-008 | Manual | P2 | Admin logged in | Open `/admin/approvals` | Page renders empty/placeholder pending admins |
| UI-ADM-009 | API | P2 | Admin logged in | Call approval/reject placeholder endpoints | Returns `status=error`, message `Not implemented` |

## 15. System, health, metrics, download testcase

| ID | Type | Priority | Preconditions | Steps | Expected result |
|---|---|---|---|---|---|
| SYS-001 | API | P0 | MongoDB running | `GET /api/v1/system/db/health` | `status=success`; `ping_ok=true`; collections listed |
| SYS-002 | API | P1 | Dev seed enabled | `GET /api/v1/system/db/seed-test` | Checks pass for users/groups/admin and zero Test room matches |
| SYS-003 | Manual/API | P0 | MongoDB stopped before startup | Start app | Startup fails fast with MongoDB init error |
| SYS-004 | API | P1 | App running | Make several API calls then check metrics endpoint | Metrics counts/latency updated |
| SYS-005 | API | P1 | Metrics available | Reset metrics endpoint if supported | Metrics reset/snapshot reflects reset |
| SYS-006 | Manual+API | P1 | SDK instruction exists | `GET /downloads/sdk/instruction` | Downloads `SDK_Instruction.md` with text/markdown |
| SYS-007 | Manual+API | P1 | SDK package files exist | `GET /downloads/sdk/zip` | Downloads `quintetx_sdk.zip` |
| SYS-008 | API | P2 | Temporarily missing SDK files in isolated env | Call SDK download zip | 404 SDK package files not found |
| SYS-009 | API | P1 | Invalid request payload | Send malformed JSON/invalid field | 422 JSON response with `status=error`, validation errors |
| SYS-010 | API | P1 | DEBUG false | Trigger unhandled internal error in test env | 500 returns generic `Internal server error` |

## 16. API response convention testcase

| ID | Type | Priority | Preconditions | Steps | Expected result |
|---|---|---|---|---|---|
| RESP-001 | API | P1 | Any success endpoint | Call endpoint | Response contains `status`, `data`, `message` |
| RESP-002 | API | P1 | Known business error | Trigger business validation error | Response `status=error`, no stacktrace |
| RESP-003 | API | P1 | Missing auth | Call protected endpoint | JSON error shape preserved |
| RESP-004 | API | P1 | Validation error | Send invalid schema | HTTP 422 with `data.errors` |

## 17. Security/authorization testcase

| ID | Type | Priority | Preconditions | Steps | Expected result |
|---|---|---|---|---|---|
| SEC-001 | API | P0 | Student token | Call admin-only create match | Rejected |
| SEC-002 | API | P0 | Student token | Call admin-only delete match | Rejected |
| SEC-003 | API | P0 | Non-leader token | Approve join request | Rejected |
| SEC-004 | API | P0 | Non-leader token | Invite/kick/rename group | Rejected |
| SEC-005 | API | P0 | Invalid agent key | Call agent state/move | HTTP 401 |
| SEC-006 | API | P1 | Valid user token | Get match details | API keys are not exposed in general match payload |
| SEC-007 | API | P1 | Browser token in localStorage | Force 401 from API client | User redirected to `/401` |
| SEC-008 | API | P1 | Malicious strings in group name/description | Create/rename group | Stored safely; UI should not execute script |
| SEC-009 | API | P1 | SQL-like/noSQL-like payload in text fields | Submit to auth/group fields | No server crash; validation/normal handling |

## 18. Regression checklist

- App starts with MongoDB running.
- Seed admin login works.
- Seed student login works.
- Student can create group.
- Student can join group via request/approval.
- Leader can invite user.
- Admin can create match.
- Agent init starts match when both sides ready.
- Valid move updates board/history/events/rev.
- Invalid move rejected.
- Win detection works in 4 directions.
- Timeout finishes match.
- Bot match works.
- Student match page updates.
- Admin dashboard/teams/rooms pages render.
- SDK instruction/zip download works.
- API errors keep consistent JSON shape.

## 19. Test execution order đề xuất

1. SYS-001, SYS-002.
2. AUTH-001 -> AUTH-014.
3. TEAM-001 -> TEAM-030.
4. NOTIF-001 -> NOTIF-006.
5. MATCH-001 -> MATCH-025.
6. AGENT-001 -> AGENT-015.
7. GAME-001 -> GAME-010.
8. BOT-001 -> BOT-005.
9. UI-STU-001 -> UI-STU-014.
10. UI-ADM-001 -> UI-ADM-009.
11. SEC-001 -> SEC-009.
12. RESP-001 -> RESP-004.

## 20. Exit criteria

Release/test pass khi:

- Tất cả P0 pass.
- P1 pass hoặc có bug ticket rõ ràng.
- Không còn lỗi auth/authorization nghiêm trọng.
- Không còn lỗi tạo match/chạy agent/win detection/timeout.
- API response shape ổn định.
- UI core flows dùng được trên trình duyệt.

## 21. Known gaps cần lưu ý khi test

- Admin approvals là placeholder, expected là `Not implemented`.
- Metrics là in-memory nên reset khi restart.
- Realtime dùng polling, không test WebSocket.
- Fine-grained match visibility chưa có; test hiện tại chỉ yêu cầu không leak API keys.
- Background heartbeat disconnect monitor chưa có trong scope test pass/fail.
