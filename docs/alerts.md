# Alerts và runbook

Các alert dưới đây dựa trên triệu chứng mà người dùng quan sát được, không phụ thuộc tên implementation nội bộ. Tất cả gửi tới Slack `#llmops-alerts` và chỉ kích hoạt khi điều kiện duy trì đủ lâu để tránh nhiễu ngắn hạn.

## Alert 1: High user latency

- **Severity:** critical
- **Duration:** 10 phút
- **Kênh:** Slack `#llmops-alerts`
- **Owner:** `llm-platform-oncall`
- **SLI/SLO:** P95 latency phải không quá 3000 ms.
- **Điều kiện:** `p95(latency_ms) > 3000` liên tục 10 phút.
- **Ảnh hưởng:** phần lớn người dùng phải chờ lâu hơn giới hạn cam kết.
- **Kiểm tra đầu tiên:** (1) xác định thời điểm P95 bắt đầu tăng trên dashboard; (2) tìm `response_sent` chậm và lấy `correlation_id`; (3) mở trace cùng ID, so sánh thời lượng `retrieve-context` và `generate-response`.
- **Mitigation:** tắt incident đang bật; nếu retrieval chậm thì chuyển sang dữ liệu fallback/cache, nếu generation chậm thì giảm giới hạn output hoặc chuyển model dự phòng.

## Alert 2: Elevated request error rate

- **Severity:** critical
- **Duration:** 5 phút
- **Kênh:** Slack `#llmops-alerts`
- **Owner:** `api-oncall`
- **SLI/SLO:** request lỗi chiếm không quá 2% tổng request.
- **Điều kiện:** error rate lớn hơn 2% liên tục 5 phút.
- **Ảnh hưởng:** người dùng nhận HTTP 500 hoặc không nhận được câu trả lời.
- **Kiểm tra đầu tiên:** (1) xem breakdown theo `error_type`; (2) lọc `request_failed` và kiểm tra `tool_success`; (3) theo `correlation_id` sang trace để xác định observation lỗi.
- **Mitigation:** tắt scenario gây lỗi, bật fallback retrieval và giảm tải/concurrency nếu dependency đang quá tải.

## Alert 3: Low response quality

- **Severity:** warning
- **Duration:** 15 phút
- **Kênh:** Slack `#llmops-alerts`
- **Owner:** `ai-quality-oncall`
- **SLI/SLO:** quality proxy trung bình phải ít nhất 0.75.
- **Điều kiện:** `mean(quality_score) < 0.75` liên tục 15 phút.
- **Ảnh hưởng:** API vẫn trả lời nhưng câu trả lời có thể thiếu context, quá ngắn hoặc không đáp ứng câu hỏi.
- **Kiểm tra đầu tiên:** (1) phân nhóm quality theo feature/model/prompt version; (2) kiểm tra retrieval output và prompt version trong trace; (3) so sánh candidate với baseline bằng cùng input.
- **Mitigation:** chuyển label `production` về prompt baseline đã xác nhận, sau đó kiểm tra lại workload trước khi promote lần nữa.
