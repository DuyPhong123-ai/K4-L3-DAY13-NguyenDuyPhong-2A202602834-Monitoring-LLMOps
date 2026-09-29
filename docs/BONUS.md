# Bonus: cost optimization, automation và audit log

## 1. Cost optimization

Ứng dụng hỗ trợ hai giới hạn tùy chọn qua `CostPolicy`:

- `LLM_MAX_CONTEXT_CHARS`: compact tài liệu retrieval trước khi compile prompt;
- `LLM_MAX_OUTPUT_TOKENS`: chặn output-token runaway ở fake LLM.

Giá trị `0` giữ nguyên hành vi baseline. Benchmark cố định seed và chạy cùng 10 request trong `data/sample_queries.jsonl`; hash workload được in để chứng minh hai nhánh dùng cùng đầu vào.

```powershell
python scripts/cost_benchmark.py --min-saving-pct 20
```

Kết quả hiện tại: cost giảm từ `0.021603 USD` xuống `0.013494 USD`, tương đương `37.54%`; input token giảm từ `536` xuống `498` và output token giảm từ `1333` xuống `800`. Đây là benchmark của fake LLM theo bảng giá mô phỏng đang dùng trong app, không phải hóa đơn provider thật.

## 2. Automation

Workflow `.github/workflows/quality-gates.yml` chạy khi push `main`, pull request hoặc chạy thủ công:

1. cài dependency;
2. chạy toàn bộ pytest;
3. validate dashboard 6/6;
4. scan secret, PII và artifact cấm;
5. chặn regression nếu mức tiết kiệm cost dưới 20%.

Security scan không in giá trị secret; nó chỉ trả loại finding và đường dẫn. `.env`, challenge chính thức, application log và audit log runtime đều bị cấm xuất hiện trong tập file Git.

```powershell
python scripts/security_scan.py
```

## 3. Audit log riêng

`app/audit.py` ghi stream riêng tại `data/audit.jsonl`, tách khỏi structured application log. Schema nằm ở `config/audit_schema.json` và bắt buộc có version, event ID, timestamp, action, outcome, actor hash, correlation ID, resource và metadata.

- Actor chỉ được lưu dưới dạng hash.
- Metadata được scrub PII trước khi ghi.
- Retention mặc định 30 ngày; record hết hạn hoặc malformed bị loại.
- Endpoint bật/tắt incident ghi cả success và failure vào audit stream.
- `scripts/query_audit.py` hỗ trợ lọc theo correlation ID, event và outcome.

Minh họa retention và query không làm bẩn log runtime:

```powershell
python scripts/audit_demo.py
python scripts/query_audit.py --correlation-id req-a1b2c3d4
```

Script demo dùng file tạm; query thứ hai dành cho audit stream runtime thực tế sau khi gọi endpoint control.
