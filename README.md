# QuintetX

Dự án Python sử dụng Poetry để quản lý dependency.

## Yêu cầu hệ thống

Trước khi bắt đầu, hãy đảm bảo máy tính của bạn đã cài đặt:

1.  **Git**: [Tải Git tại đây](https://git-scm.com/downloads)
2.  **Python 3.12+**: [Tải Python tại đây](https://www.python.org/downloads/)
    *   *Lưu ý khi cài đặt Python trên Windows: Nhớ tích chọn **"Add Python to PATH"**.*

## Cài đặt

### 1. Cài đặt Poetry

Poetry là công cụ quản lý thư viện và gói cho Python. Mở terminal (PowerShell, CMD hoặc Terminal trên VS Code/JetBrains) và chạy lệnh sau:

**Windows (PowerShell):**
```powershell
(Invoke-WebRequest -Uri https://install.python-poetry.org -UseBasicParsing).Content | python -
```

**Linux / macOS / Unix:**
```bash
curl -sSL https://install.python-poetry.org | python3 -
```

Sau khi cài đặt xong, bạn có thể cần khởi động lại terminal hoặc thêm Poetry vào biến môi trường PATH theo hướng dẫn trên màn hình.

Kiểm tra cài đặt bằng lệnh:
```bash
poetry --version
```

### 2. Clone project

Mở terminal tại thư mục bạn muốn lưu dự án và chạy:

```bash
git clone https://github.com/Start-0/QuintetX.git
cd QuintetX
```

### 3. Cài đặt thư viện (Dependencies)

Tại thư mục gốc của dự án (nơi có file `pyproject.toml`), chạy lệnh:

```bash
poetry install
```

Lệnh này sẽ tạo môi trường ảo (virtualenv) và cài đặt tất cả các thư viện cần thiết.

## Hướng dẫn chạy dự án

### 0. Khởi động MongoDB local (bắt buộc)

Ứng dụng hiện cấu hình **fail fast** khi startup: nếu không kết nối được MongoDB thì server sẽ raise exception và dừng ngay.

Trước khi chạy app, hãy đảm bảo MongoDB local đang hoạt động ở địa chỉ mặc định:

```text
mongodb://localhost:27017
```

Bạn có thể tạo file `.env` ở thư mục gốc để override cấu hình nếu cần:

```env
MONGODB_URI=mongodb://localhost:27017
DATABASE_NAME=quintetx
MONGODB_SERVER_SELECTION_TIMEOUT_MS=60000
```

Khi startup thành công lần đầu, hệ thống sẽ tự khởi tạo database theo cơ chế idempotent:
- Nếu collection/index đã tồn tại thì bỏ qua.
- Seed local chỉ tạo nếu chưa có.
- Seed mặc định: 3 user, 2 team (1 team 2 người, 1 team 1 người), 0 match.

### Cách 1: Chạy bằng dòng lệnh (Terminal)

Để chạy file `main.py` trong môi trường của Poetry:

```bash
poetry run python main.py
```

Hoặc kích hoạt shell của môi trường ảo trước:
```bash
poetry shell
python main.py
```

### Cách 2: Cấu hình trên IDE

#### Visual Studio Code (VS Code)
1.  Cài đặt Extension **Python** của Microsoft.
2.  Mở thư mục dự án `QuintetX` bằng VS Code.
3.  Mở file `main.py`.
4.  Nhìn xuống góc dưới bên phải, click vào phiên bản Python (Select Interpreter).
5.  Chọn interpreter có đường dẫn chứa `.venv` hoặc được đánh dấu là (Poetry). Nếu chưa thấy, hãy chạy lệnh `poetry env info --path` trong terminal để lấy đường dẫn môi trường ảo, sau đó chọn "Enter interpreter path" và dán vào.
6.  Nhấn phím `F5` hoặc nút Run để chạy.

#### JetBrains IDE (PyCharm / IntelliJ IDEA)
1.  Mở thư mục dự án bằng PyCharm/IntelliJ.
2.  IDE thường sẽ tự động phát hiện file `pyproject.toml` và đề xuất cài đặt môi trường Poetry.
3.  Nếu không tự động:
    *   Vào **Settings/Preferences** -> **Project: QuintetX** -> **Python Interpreter**.
    *   Click icon bánh răng -> **Add...**
    *   Chọn **Poetry Environment**.
    *   Chọn **Existing environment** (nếu đã chạy `poetry install`) hoặc để nó tự tạo mới.
4.  Mở file `main.py`.
5.  Click chuột phải chọn **Run 'main'** hoặc nhấn `Shift + F10`.

## Quản lý thư viện

Để thêm một thư viện mới vào dự án (ví dụ: `requests`):

```bash
poetry add requests
```

Để thêm thư viện chỉ dùng cho development (ví dụ: `pytest`):

```bash
poetry add --group dev pytest
```

Để gỡ cài đặt một thư viện:

```bash
poetry remove requests
```

## API Auth Requests

Tai lieu request/response cho dang ky, dang nhap:

- docs/auth-api.md

## Cấu trúc dự án

```
QuintetX/
├── app/
│   └── core/
│       └── config.py          # Cấu hình backend (FastAPI)
├── static/                    # Tệp tĩnh (CSS/JS/Images)
│   ├── favicon.svg            # Favicon chính
│   ├── favicon.ico            # Favicon fallback
│   └── js/
│       └── config.js          # Cấu hình frontend
├── templates/                 # Giao diện HTML (Jinja2)
│   └── base.html              # Layout chính
├── main.py                    # Entry point của ứng dụng
├── pyproject.toml             # Quản lý dependency (Poetry)
├── poetry.lock                # Lockfile của Poetry
└── README.md                  # Tài liệu dự án
```
