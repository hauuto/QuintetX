# Auth API Requests

Tai lieu nay mo ta cac request auth de frontend/Postman goi len server.
Tat ca response deu theo format:

```json
{
  "status": "success|error",
  "data": {},
  "message": ""
}
```

## Base URL

- Local: http://127.0.0.1:8000

## 1) Dang ky sinh vien

- Method: POST
- URL: /api/v1/auth/register/student
- Content-Type: application/json

Rang buoc:
- mssv phai dung 8 chu so, vi du 23012345
- user.id duoc tao theo format U + mssv

Request body:

```json
{
  "mssv": "22123456",
  "full_name": "Nguyen Van A",
  "class_name": "D21CQCN01-N",
  "password": "MySecret123",
  "confirm_password": "MySecret123"
}
```

Success response:

```json
{
  "status": "success",
  "data": {
    "user": {
      "id": "U22123456",
      "mssv": "22123456",
      "full_name": "Nguyen Van A",
      "class_name": "D21CQCN01-N",
      "role": "student"
    }
  },
  "message": ""
}
```

Error cases:
- MSSV da ton tai
- Password va confirm_password khong khop
- MSSV sai dinh dang 8 chu so

## 2) Dang nhap sinh vien

- Method: POST
- URL: /api/v1/auth/login/student
- Content-Type: application/json

Request body:

```json
{
  "mssv": "22123456",
  "password": "MySecret123"
}
```

Success response:

```json
{
  "status": "success",
  "data": {
    "access_token": "generated_token",
    "token_type": "bearer",
    "expires_in_minutes": 30,
    "user": {
      "id": "0c4d4f5b-0bb2-42dc-bf43-7f0a8ccf7ec3",
      "mssv": "22123456",
      "full_name": "Nguyen Van A",
      "class_name": "D21CQCN01-N",
      "role": "student"
    }
  },
  "message": ""
}
```

Error cases:
- Sai MSSV hoac password
- Tai khoan da bi vo hieu hoa (is_active=false)

## 3) Dang nhap admin

- Method: POST
- URL: /api/v1/auth/login/admin
- Content-Type: application/json

Request body:

```json
{
  "username_or_email": "admin@example.com",
  "password": "AdminSecret123"
}
```

Success response:

```json
{
  "status": "success",
  "data": {
    "access_token": "generated_token",
    "token_type": "bearer",
    "expires_in_minutes": 30,
    "user": {
      "id": "admin-id",
      "full_name": "System Admin",
      "role": "admin"
    }
  },
  "message": ""
}
```

Error cases:
- Sai username_or_email hoac password
- Tai khoan khong co role admin
- Tai khoan da bi vo hieu hoa (is_active=false)

## Curl nhanh

Dang ky sinh vien:

```bash
curl -X POST "http://127.0.0.1:8000/api/v1/auth/register/student" \
  -H "Content-Type: application/json" \
  -d '{
    "mssv": "22123456",
    "full_name": "Nguyen Van A",
    "class_name": "D21CQCN01-N",
    "password": "MySecret123",
    "confirm_password": "MySecret123"
  }'
```

Dang nhap sinh vien:

```bash
curl -X POST "http://127.0.0.1:8000/api/v1/auth/login/student" \
  -H "Content-Type: application/json" \
  -d '{
    "mssv": "22123456",
    "password": "MySecret123"
  }'
```

Dang nhap admin:

```bash
curl -X POST "http://127.0.0.1:8000/api/v1/auth/login/admin" \
  -H "Content-Type: application/json" \
  -d '{
    "username_or_email": "admin@example.com",
    "password": "AdminSecret123"
  }'
```

## Luu y

- access_token hien tai la token tam de bat dau backend flow.
- Buoc tiep theo nen thay bang JWT ky bang SECRET_KEY.
- Password duoc hash theo PBKDF2 truoc khi luu vao MongoDB.

## Group Management API (JWT Bearer)

Tat ca API ben duoi can header:

```text
Authorization: Bearer <access_token>
```

1) GET /api/v1/groups/open-missing
- Tra danh sach group cong khai va chua du 6 thanh vien.

1.1) GET /api/v1/groups/me
- Tra ve group hien tai cua user dang dang nhap.
- Neu chua co group: group = null.

2) POST /api/v1/groups
- Tao group moi.
- Body: {"name", "description", "avatar_url", "is_public"}

3) POST /api/v1/groups/{group_id}/join
- Rule hien tai: group public van gui join request.
- Group private: khong join truc tiep, chi vao bang invite.

4) GET /api/v1/groups/{group_id}/join-requests
- Chi leader xem danh sach nguoi xin vao.

5) POST /api/v1/groups/{group_id}/join-requests/{user_id}/approve

6) POST /api/v1/groups/{group_id}/join-requests/{user_id}/reject

7) GET /api/v1/groups/players/search?mssv=23012345
- Tra ve player = null | thong tin user.
- Bao gom trang thai has_group va group_id.

8) POST /api/v1/groups/{group_id}/invite
- Body: {"mssv": "23012345"}

9) POST /api/v1/groups/invites/{notification_id}/accept

10) POST /api/v1/groups/invites/{notification_id}/reject

11) PATCH /api/v1/groups/{group_id}/name
- Body: {"name": "Ten moi"}

12) DELETE /api/v1/groups/{group_id}/members/{member_user_id}
- Leader co the kick thanh vien (khong kick chinh leader).
