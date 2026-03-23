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
- MSSV da ton tai
- Password va confirm_password khong khop

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
