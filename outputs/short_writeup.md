# Bài viết ngắn — GPU FinOps Optimization cho NimbusAI

## 1. Baseline so với phương án tối ưu

Trong kịch bản hiện tại, tổng chi phí GPU và inference của NimbusAI là **$27,133/tháng**. Sau khi áp dụng cascade, cache có kiểm tra hiệu quả kinh tế, Batch API, chiến lược mua spot/reserved, right-sizing và tắt GPU nhàn rỗi, chi phí dự kiến còn **$14,751/tháng**. Như vậy, NimbusAI có thể tiết kiệm khoảng **$12,382/tháng**, tương đương **45.6%** baseline.

Đối với inference, chỉ số quan trọng hơn giá một GPU-giờ là chi phí trên một triệu token. Baseline chạy mọi request trên model lớn, không cache và không batch có chi phí **$6.488/1M-token**. Phương án tối ưu đạt **$1.202/1M-token**, giảm khoảng **81.5%**. Kết quả này đã bao gồm chi phí tạo cache; vì vậy nó thận trọng và thực tế hơn kết quả cũ `$1.126/1M-token`, vốn chỉ tính cache read mà bỏ qua cache write.

## 2. Phân tích từng đòn bẩy

| Đòn bẩy | Tiết kiệm dự kiến/tháng | Tỷ trọng trong tổng savings |
|---|---:|---:|
| Purchasing: spot và reserved | $8,055 | 65.1% |
| Right-sizing theo MBU, VRAM và bandwidth | $2,532 | 20.4% |
| Inference: cascade, cache và batch | $1,195 | 9.7% |
| Tắt GPU nhàn rỗi | $600 | 4.8% |
| **Tổng** | **$12,382** | **100%** |

Đòn bẩy đóng góp lớn nhất là **purchasing**, chiếm khoảng 65% tổng mức tiết kiệm. Nguyên nhân là các workload training có thể gián đoạn có số lượng GPU và GPU-hours lớn, nên chuyển chúng sang spot tạo ra chênh lệch tuyệt đối lớn. Các workload inference chạy ổn định cũng hưởng lợi từ reserved pricing. Tuy nhiên, không nên phóng đại savings bằng cách dùng giá reserved ba năm cho workload chỉ quan sát trong thời gian ngắn; policy mới dùng mức một năm cho các job có horizon dưới ba năm, khiến M3 savings giảm từ **39.1% xuống 31.4%** nhưng đáng tin cậy hơn.

Right-sizing đứng thứ hai. Phương án này chỉ chọn GPU thay thế khi GPU mới có đủ VRAM, peak bandwidth cao hơn bandwidth đã quan sát, đồng thời có cả giá theo giờ và `$/GB-VRAM` thấp hơn. Inference optimization có tỷ trọng tiền nhỏ hơn vì tổng hóa đơn token nhỏ hơn hóa đơn GPU, nhưng lại tạo cải thiện lớn nhất cho unit economics: `$6.488 → $1.202/1M-token`. Việc tắt GPU idle có giá trị thấp nhất nhưng nên thực hiện sớm vì đơn giản, ít rủi ro và tiết kiệm ngay.

## 3. GPU-Util Lie và tác động tài chính

Hai GPU bị phát hiện có GPU-Util từ 90% trở lên nhưng MFU dưới 30% là:

- `gpu-h100-4`: GPU-Util **98.2%**, nhưng MFU chỉ **19.4%** và MBU **20.7%**.
- `gpu-a10g-1`: GPU-Util **96.9%**, nhưng MFU chỉ **26.8%** và MBU **30.2%**.

GPU-Util cao chỉ cho biết GPU đang bận hoặc clock đang hoạt động; nó không chứng minh phần lớn FLOPs hữu ích đang được sử dụng. Memory stall, kernel overhead, batch quá nhỏ hoặc pipeline/I/O không hiệu quả đều có thể làm GPU báo bận trong khi MFU thấp. Vì vậy, nếu chỉ quan sát `nvidia-smi`, NimbusAI có thể tiếp tục trả giá GPU cao mà không nhận được throughput tương ứng.

Theo feasibility screen của phần right-sizing, `gpu-h100-4` có thể chuyển từ H100 sang MI300X và tiết kiệm khoảng **$396/tháng**; `gpu-a10g-1` có thể chuyển từ A10G sang L4 và tiết kiệm khoảng **$144/tháng**. Riêng hai GPU bị “lie” có tiềm năng tiết kiệm **$540/tháng**. Con số này chưa phải cam kết chắc chắn: peak bandwidth chỉ chứng minh ứng viên có khả năng đáp ứng bandwidth đã quan sát, không chứng minh latency và throughput thực tế sẽ giữ nguyên. NimbusAI cần benchmark và canary trước khi chuyển production.

## 4. Các phần mở rộng đã thực hiện

### Extension 1 — Purchasing theo interruption risk và duration

`recommend_tier()` đã được mở rộng để dùng interruption rate riêng cho từng GPU và phân biệt reserved một năm với ba năm. Các rate 3% cho H100, 6% cho A100 và 10% cho A10G là **giả định planning**, không phải SLA của nhà cung cấp. Các job spot vẫn giữ nguyên tier nhưng chi phí thay đổi theo rủi ro của từng GPU. Ba job inference ổn định chuyển cách tính từ `reserved_3yr` sang `reserved_1yr`, khiến optimized M3 tăng từ **$15,627 lên $17,612/tháng-equivalent**, và savings giảm từ **39.1% xuống 31.4%**. Insight quan trọng là một phương án tiết kiệm thấp hơn nhưng đúng commitment horizon có giá trị hơn con số savings cao dựa trên mức giá không đủ điều kiện sử dụng.

### Extension 2 — Right-sizing theo MBU

Policy right-sizing đọc `hbm_gb`, `peak_bw_tbs` và `on_demand_hr` từ price catalog. Do telemetry không có memory occupancy, dung lượng cần thiết được đặt thận trọng bằng toàn bộ HBM của GPU hiện tại. Kết quả đề xuất sáu H100 sang MI300X và hai A10G sang L4, với tổng tiềm năng **$2,532/tháng**. Insight chính là không thể chỉ chọn GPU có giá giờ thấp nhất: GPU thay thế phải chứa được workload và đáp ứng bandwidth. Dù vượt qua các điều kiện này, phương án vẫn cần benchmark vì khác biệt kiến trúc và phần mềm có thể ảnh hưởng throughput.

### Extension 3 — Kinh tế học của cache

Hàm `cache_is_worth_it()` chỉ bật cache khi tổng tiền tiết kiệm từ các lượt đọc lớn hơn chi phí ghi. Vì CSV không chứa prefix ID hoặc reads per prefix, phân tích giả định cache write bằng **1.25 lần** giá input thường, small tier có trung bình một read và large tier có bốn reads. Ngưỡng hòa vốn là **1.39 reads/prefix**: cache bị tắt cho small tier và được bật cho large tier. Với một read, optimized cost là **$1.282/1M-token**; với tám reads, chi phí giảm còn **$1.154/1M-token**. Policy hỗn hợp thực tế đạt **$1.202/1M-token**. Insight chính là cache hit không tự động đồng nghĩa với tiết kiệm; prefix ít tái sử dụng có thể không hoàn lại cache write cost.

## 5. Ba hành động ưu tiên cho NimbusAI

1. **Áp dụng purchasing policy cho các job có thể gián đoạn.** Bắt đầu với training và batch evaluation, bật checkpoint, theo dõi interruption thực tế theo GPU/region và chỉ ký reserved sau khi xác nhận workload ổn định đủ lâu. Đây là đòn bẩy lớn nhất với khoảng **$8,055/tháng** savings.

2. **Chạy benchmark right-sizing theo từng workload.** Canary H100 → MI300X và A10G → L4, so sánh throughput, latency, error rate và chi phí trên token. Chỉ rollout khi SLO được giữ nguyên; tiềm năng đo được là **$2,532/tháng**.

3. **Thiết lập governance cho inference và idle capacity.** Route request đơn giản sang model nhỏ, dùng Batch API cho traffic không cần realtime, chỉ cache prefix vượt ngưỡng reuse, và tự động tắt GPU idle. Dashboard nên theo dõi `$/1M-token`, MFU/MBU, tag coverage và cache reads/prefix thay vì chỉ theo dõi GPU-Util.

Về sustainability, phép tính hiện tại cho một query 800 token là khoảng **0.24 Wh** và **0.091 gCO2e** tại `us-east-1`. Trong dữ liệu minh họa, `europe-north1` là vùng sạch nhất ở **30 gCO2/kWh**, còn `us-east-wa` có giá điện thấp nhất ở **$0.055/kWh**; do đó “rẻ nhất” và “sạch nhất” là hai tiêu chí khác nhau và cần được cân bằng với latency, data residency và khả năng cung ứng GPU.

_Các mức giá, interruption rate và carbon intensity là snapshot/giả định phục vụ bài lab. Cần re-baseline bằng dữ liệu nhà cung cấp và benchmark production trước khi triển khai._
