![Platform](https://img.shields.io/badge/platform-Windows-blue) [![Release](https://img.shields.io/badge/Release-V1.0-fc1ba6)](https://github.com/yoons100/ndi-ptz-controller/releases) ![License](https://img.shields.io/github/license/yoons100/ndi-ptz-controller)
# NDI PTZ Controller

## Overview

NDI PTZ Controller is a desktop application designed for controlling NDI-enabled PTZ cameras in real time.
It provides an intuitive interface for camera selection, PTZ control, preset management, and live preview within a single application window.

---

## Features

* Control multiple NDI PTZ cameras (up to 4)
* Real-time PTZ control using keyboard (arrow keys and zoom)
* Preset recall and store (1–8 keys)
* Custom preset naming for each camera
* Global preset control for all connected cameras
* In-app low-latency NDI preview (16:9 optimized)
* Automatic camera reconnection based on saved configuration
* OSC control support
* Config file auto-save and restore
* NDI Studio Monitor quick launch

---

## Keyboard Shortcuts

* Ctrl + 1~4 : Select camera
* 1~8 : Recall preset
* Shift + 1~8 : Store preset
* Arrow keys : Pan / Tilt
* `+` / `-` : Zoom

Note: Hotkeys are active only when the application window is focused.

---

## Preset Label Editing

* Ctrl + Click on preset button to rename
* Supports custom text display under preset numbers
* Applies to both individual camera presets and global presets

---

## OSC Control

Supports OSC commands for remote triggering.

Examples:

```
/cam1/preset/1
```

Default port: 9000

---

## Configuration

* Config file is automatically created in the same folder as the executable:

```
ndi_ptz_controller_config.json
```

* Stores:

  * Camera source names
  * Preset labels
  * Global preset labels

---

## Notes

* Some cameras may take a few seconds after connection before PTZ becomes available
* If preview does not appear immediately, wait briefly for the stream to initialize
* For best performance, use wired network connections

---
<img width="882" height="724" alt="2026-04-22 17 06 06" src="https://github.com/user-attachments/assets/25bce462-d678-48b0-9dbd-07efab8088f2" />

---

# NDI PTZ Controller

## 개요

NDI PTZ Controller는 NDI 기반 PTZ 카메라를 실시간으로 제어하기 위한 데스크톱 애플리케이션입니다.
카메라 선택, PTZ 제어, 프리셋 관리, 실시간 프리뷰 기능을 하나의 인터페이스에서 제공합니다.

---

## 주요 기능

* 최대 4대의 NDI PTZ 카메라 제어
* 키보드를 이용한 실시간 PTZ 제어
* 프리셋 호출 및 저장 (1–8번 키)
* 카메라별 프리셋 이름 사용자 정의
* 전체 카메라 동시 프리셋 제어
* 앱 내부 저지연 NDI 프리뷰 (16:9 최적화)
* 설정 기반 자동 카메라 재연결
* OSC 제어 지원
* 설정 파일 자동 저장 및 복원
* NDI Studio Monitor 실행 기능

---

## 단축키

* Ctrl + 1~4 : 카메라 선택
* 1~8 : 프리셋 호출
* Shift + 1~8 : 프리셋 저장
* 방향키 : 팬 / 틸트
* `+` / `-` : 줌

참고: 단축키는 앱 창이 활성화된 상태에서만 동작합니다.

---

## 프리셋 이름 수정

* 프리셋 버튼을 Ctrl + 클릭하여 이름 수정
* 숫자 아래에 사용자 정의 텍스트 표시 가능
* 개별 카메라 및 전체 프리셋 모두 적용

---

## OSC 제어

OSC를 이용한 외부 제어 지원

예시:

```
/cam1/preset/1
```

기본 포트: 9000

---

## 설정 파일

* 실행 파일과 동일한 폴더에 자동 생성:

```
ndi_ptz_controller_config.json
```

* 저장 항목:

  * 카메라 소스 정보
  * 프리셋 이름
  * 전체 프리셋 이름

---

## 참고 사항

* 일부 카메라는 연결 후 PTZ 제어가 활성화되기까지 몇 초가 걸릴 수 있습니다
* 프리뷰가 바로 표시되지 않으면 잠시 대기하세요
* 안정적인 사용을 위해 유선 네트워크를 권장합니다

---

