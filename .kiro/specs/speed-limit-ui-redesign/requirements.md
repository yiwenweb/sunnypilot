# Requirements Document

## Introduction

本文档定义了 sunnypilot Qt C++ UI 限速标志显示功能的改进需求（B方案），旨在解决当前A方案（2026-07-13实现）中存在的视觉拥挤、缺少超速警告、前方限速提示不直观等问题。改进后的限速UI将独立显示、提供超速视觉反馈、前方限速预告，并保持与现有HUD元素（转向弧、车道线距离、AccelBar等）的视觉协调性。

## Glossary

- **SpeedLimit_UI**: 限速标志显示模块，负责在HUD上渲染当前限速标志
- **ACC_SetSpeed**: 自适应巡航控制（ACC）的设定速度显示模块
- **HudRendererSP**: sunnypilot HUD渲染器类，负责onroad页面所有HUD元素的绘制
- **liveMapDataSP**: sunnypilot扩展的地图数据消息服务，包含当前限速和前方限速信息
- **carState**: 车辆状态消息服务，包含当前车速信息
- **OSM**: OpenStreetMap 地图数据
- **Visual_Recognition**: 基于摄像头的视觉识别系统
- **Overspeed_Warning**: 超速警告，当前车速超过限速时的视觉反馈
- **Upcoming_SpeedLimit**: 前方限速，指即将到达路段的限速值
- **Confidence_Indicator**: 可信度指示器，用于区分限速数据来源的可靠性
- **C3**: Comma Three 硬件设备，分辨率1920×1080
- **HUD**: Head-Up Display 抬头显示，驾驶界面上的信息叠加层

## Requirements

### Requirement 1: 独立限速标志显示区域

**User Story:** 作为驾驶员，我希望限速标志与ACC设定速度分离显示，以便清晰地区分两种不同的信息。

#### Acceptance Criteria

1. THE SpeedLimit_UI SHALL render in a separate display area from ACC_SetSpeed
2. THE SpeedLimit_UI SHALL NOT share the same bounding box with ACC_SetSpeed
3. WHEN SpeedLimit parameter is enabled AND speedLimitValid is true, THE SpeedLimit_UI SHALL display the speed limit sign
4. THE SpeedLimit_UI SHALL maintain consistent visual style with existing HUD elements (rounded corners, semi-transparent background)
5. THE SpeedLimit_UI SHALL use Tesla-style white rounded rectangle background for the speed limit number

### Requirement 2: 超速视觉警告

**User Story:** 作为驾驶员，我希望在超速时得到明显的视觉警告，以便及时调整车速。

#### Acceptance Criteria

1. WHEN current vehicle speed exceeds speed limit by 10 km/h or more AND speed limit is less than 20 km/h, THE SpeedLimit_UI SHALL change the sign border color to orange
2. WHEN current vehicle speed exceeds speed limit by 20 km/h or more, THE SpeedLimit_UI SHALL change the sign border color to red
3. WHEN current vehicle speed exceeds speed limit by 10 km/h or more, THE SpeedLimit_UI SHALL increase the sign size by 10 percent
4. WHEN current vehicle speed exceeds speed limit by 20 km/h or more, THE SpeedLimit_UI SHALL increase the sign size by 20 percent
5. THE SpeedLimit_UI SHALL use smooth transition animation for color and size changes within 300 milliseconds
6. WHEN vehicle speed returns below the overspeed threshold, THE SpeedLimit_UI SHALL restore normal appearance within 300 milliseconds

### Requirement 3: 前方限速预告

**User Story:** 作为驾驶员，我希望提前知道前方限速变化，以便平稳调整车速。

#### Acceptance Criteria

1. WHEN speedLimitAheadValid is true AND speedLimitAhead differs from current speedLimit by 10 km/h or more, THE SpeedLimit_UI SHALL display the upcoming speed limit value
2. THE SpeedLimit_UI SHALL display upcoming speed limit below the current speed limit with an arrow indicator
3. WHEN speedLimitAhead is lower than current speedLimit, THE SpeedLimit_UI SHALL use yellow color for the upcoming value
4. WHEN speedLimitAhead is higher than current speedLimit, THE SpeedLimit_UI SHALL use green color for the upcoming value
5. THE SpeedLimit_UI SHALL use font size of 24pt for the upcoming speed limit value

### Requirement 4: 数据来源可信度指示

**User Story:** 作为驾驶员，我希望了解限速数据的来源和可靠性，以便判断是否需要额外关注路况。

#### Acceptance Criteria

1. WHEN speedLimitSource indicates OSM map data, THE SpeedLimit_UI SHALL display a map icon with 80 percent opacity
2. WHEN speedLimitSource indicates Visual_Recognition, THE SpeedLimit_UI SHALL display a camera icon with 100 percent opacity
3. THE SpeedLimit_UI SHALL position the source indicator icon at the top-right corner of the speed limit sign
4. THE Confidence_Indicator icon SHALL have a size of 20×20 pixels
5. WHEN speedLimitSource is unknown or not available, THE SpeedLimit_UI SHALL NOT display any source indicator icon

### Requirement 5: 布局协调性

**User Story:** 作为驾驶员，我希望限速标志不遮挡其他HUD元素，以便同时查看多个信息。

#### Acceptance Criteria

1. THE SpeedLimit_UI SHALL NOT overlap with ACC_SetSpeed display area
2. THE SpeedLimit_UI SHALL NOT overlap with SteeringArc display area
3. THE SpeedLimit_UI SHALL NOT overlap with LaneLineData display area
4. THE SpeedLimit_UI SHALL NOT overlap with AccelBar display area
5. THE SpeedLimit_UI SHALL NOT overlap with DevUI right-side indicators when DevUIInfo is 1 or 2
6. THE SpeedLimit_UI SHALL NOT overlap with DevUI bottom indicators when DevUIInfo is 2
7. THE SpeedLimit_UI SHALL position at coordinates that maintain at least 20 pixels clearance from all existing HUD elements

### Requirement 6: 公制和英制单位支持

**User Story:** 作为使用不同单位系统的驾驶员，我希望限速标志根据系统设置正确显示单位。

#### Acceptance Criteria

1. WHEN is_metric is true, THE SpeedLimit_UI SHALL convert speedLimit from m/s to km/h using factor 3.6
2. WHEN is_metric is false, THE SpeedLimit_UI SHALL convert speedLimit from m/s to mph using factor 2.237
3. THE SpeedLimit_UI SHALL display the speed limit value as an integer without decimal places
4. THE SpeedLimit_UI SHALL NOT display unit suffix (km/h or mph) on the speed limit sign
5. WHEN speedLimitAhead is displayed, THE SpeedLimit_UI SHALL apply the same unit conversion as the current speed limit

### Requirement 7: 性能要求

**User Story:** 作为系统，我需要确保限速UI不影响HUD帧率，以便保持流畅的驾驶界面体验。

#### Acceptance Criteria

1. THE SpeedLimit_UI SHALL complete all drawing operations within 5 milliseconds per frame
2. THE SpeedLimit_UI SHALL NOT cause HUD frame rate to drop below 18 fps on C3 hardware
3. THE SpeedLimit_UI SHALL use pre-calculated values for size transitions to avoid per-frame trigonometric calculations
4. THE SpeedLimit_UI SHALL cache QColor and QPen objects for reuse across frames
5. THE SpeedLimit_UI SHALL use linear interpolation for smooth animations instead of exponential or bezier curves

### Requirement 8: 参数持久化

**User Story:** 作为驾驶员，我希望限速显示开关设置在系统重启后保持，以便不需要每次重新配置。

#### Acceptance Criteria

1. THE System SHALL register SpeedLimit parameter in common/params_keys.h with PERSISTENT flag
2. THE System SHALL register SpeedLimit parameter in common/params_keys.h with BACKUP flag
3. THE System SHALL set default value of SpeedLimit parameter to "0" (disabled)
4. THE System SHALL recompile params_pyx.so after adding SpeedLimit parameter to ensure manager persistence
5. WHEN SpeedLimit parameter is modified in settings, THE System SHALL persist the new value across reboots

### Requirement 9: 消息服务订阅

**User Story:** 作为系统，我需要正确订阅限速数据消息服务，以便避免onroad崩溃。

#### Acceptance Criteria

1. THE HudRendererSP SHALL subscribe to liveMapDataSP service in UIStateSP constructor
2. THE HudRendererSP SHALL check sm.rcv_frame("liveMapDataSP") is greater than 0 before accessing speedLimit data
3. THE HudRendererSP SHALL check sm.rcv_frame("carState") is greater than 0 before accessing vehicle speed data
4. WHEN liveMapDataSP service is not available, THE SpeedLimit_UI SHALL NOT attempt to render the speed limit sign
5. WHEN speedLimit field is not initialized in liveMapDataSP, THE SpeedLimit_UI SHALL NOT crash the UI process

### Requirement 10: 设置面板集成

**User Story:** 作为驾驶员，我希望在设置面板中控制限速显示功能，以便根据个人偏好启用或禁用该功能。

#### Acceptance Criteria

1. THE SP_Features_Panel SHALL provide a toggle control for SpeedLimit parameter
2. THE SpeedLimit toggle SHALL display title "限速标志显示" in Chinese
3. THE SpeedLimit toggle SHALL display description "显示当前道路限速标志，超速时提供视觉警告" in Chinese
4. WHEN SpeedLimit toggle is enabled, THE System SHALL set SpeedLimit parameter to "1"
5. WHEN SpeedLimit toggle is disabled, THE System SHALL set SpeedLimit parameter to "0"
6. THE SpeedLimit toggle SHALL reflect the current parameter value when the settings panel is opened

### Requirement 11: 限速数据有效性检查

**User Story:** 作为系统，我需要验证限速数据的有效性，以便避免显示错误或无效的限速值。

#### Acceptance Criteria

1. THE SpeedLimit_UI SHALL check speedLimitValid is true before displaying current speed limit
2. THE SpeedLimit_UI SHALL check speedLimitAheadValid is true before displaying upcoming speed limit
3. WHEN speedLimit value is 0 m/s, THE SpeedLimit_UI SHALL treat it as invalid data
4. WHEN speedLimit value is greater than 200 km/h (55.6 m/s), THE SpeedLimit_UI SHALL treat it as invalid data
5. WHEN speedLimit data is invalid, THE SpeedLimit_UI SHALL NOT display the speed limit sign
6. THE SpeedLimit_UI SHALL use speedLimitValid flag from liveMapDataSP without additional validation logic

### Requirement 12: 超速阈值计算

**User Story:** 作为系统，我需要准确计算超速阈值，以便触发正确的警告级别。

#### Acceptance Criteria

1. THE SpeedLimit_UI SHALL calculate overspeed amount as (current_speed - speed_limit) in the same unit
2. WHEN speed limit is less than 60 km/h, THE SpeedLimit_UI SHALL use absolute threshold of 10 km/h for orange warning
3. WHEN speed limit is 60 km/h or greater, THE SpeedLimit_UI SHALL use relative threshold of 15 percent for orange warning
4. THE SpeedLimit_UI SHALL use absolute threshold of 20 km/h for red warning regardless of speed limit value
5. THE SpeedLimit_UI SHALL apply a 2-second hysteresis delay before transitioning from warning state to normal state
6. THE SpeedLimit_UI SHALL NOT apply hysteresis delay when transitioning from normal state to warning state

### Requirement 13: 动画平滑过渡

**User Story:** 作为驾驶员，我希望限速标志的颜色和尺寸变化流畅自然，以便不会因为突变而分散注意力。

#### Acceptance Criteria

1. THE SpeedLimit_UI SHALL use linear interpolation with alpha value of 0.15 for color transitions
2. THE SpeedLimit_UI SHALL use linear interpolation with alpha value of 0.2 for size transitions
3. THE SpeedLimit_UI SHALL update interpolated values in updateState method before drawing
4. THE SpeedLimit_UI SHALL clamp interpolated size values between 100 percent and 120 percent of base size
5. THE SpeedLimit_UI SHALL clamp interpolated alpha values between 0 and 255

### Requirement 14: 前方限速箭头指示器

**User Story:** 作为驾驶员，我希望前方限速显示清晰的方向指示，以便理解这是即将到达的限速而非当前限速。

#### Acceptance Criteria

1. THE SpeedLimit_UI SHALL draw a downward-pointing arrow between current speed limit and upcoming speed limit
2. THE arrow SHALL use the same color as the upcoming speed limit value (yellow for decrease, green for increase)
3. THE arrow SHALL have a height of 16 pixels and width of 12 pixels
4. THE arrow SHALL be vertically centered between the current limit and upcoming limit
5. THE arrow SHALL use antialiasing for smooth rendering

### Requirement 15: 限速标志位置定义

**User Story:** 作为开发者，我需要明确限速标志的屏幕坐标，以便实现与其他HUD元素的空间协调。

#### Acceptance Criteria

1. THE SpeedLimit_UI SHALL position at x-coordinate of 60 pixels from left edge of screen
2. THE SpeedLimit_UI SHALL position at y-coordinate of 280 pixels from top edge of screen
3. THE SpeedLimit_UI SHALL have a base width of 140 pixels in metric mode
4. THE SpeedLimit_UI SHALL have a base height of 180 pixels
5. WHEN overspeed warning is active, THE SpeedLimit_UI SHALL expand symmetrically from the center point
6. THE SpeedLimit_UI SHALL use border radius of 24 pixels for rounded corners
