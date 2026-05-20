![Platform](https://img.shields.io/badge/platform-Windows-blue) [![Release](https://img.shields.io/badge/Release-V1.64-fc1ba6)](https://github.com/yoons100/ndi-ptz-controller/releases) ![License](https://img.shields.io/github/license/yoons100/ndi-ptz-controller)
# <img width="40" height="40" alt="ndi" src="https://github.com/user-attachments/assets/4e51216c-2e5a-4e66-8739-1143695a5e4a" /> NDI PTZ Controller
```
 When you run this app for the first time, you may see a warning because it is not digitally signed.  
 A signed version of the app is available on the Microsoft Store.
```
<a href="https://get.microsoft.com/installer/download/9p0kjgjbfhnp?referrer=appbadge" target="_self" >
	<img src="https://get.microsoft.com/images/en-us%20dark.svg" width="200"/>
</a>  

https://apps.microsoft.com/detail/9P0KJGJBFHNP

## Overview

NDI PTZ Controller is a Windows App designed for controlling NDI-enabled PTZ cameras in real time.
It provides an intuitive interface for camera selection, PTZ control, preset management, and live preview within a single application window.

---

## Features

* Control multiple NDI PTZ cameras (up to 4)
* Real-time PTZ control using keyboard (arrow keys and zoom)
* Preset recall and store (1–8 keys)
* Custom preset naming for each camera
* Global preset control for all connected cameras
* In-app low-latency NDI preview
* Automatic camera reconnection based on saved configuration
* OSC control support
* Config file auto-save and restore
* NDI Studio Monitor quick launch
* NDI Multiview Popup window

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

* Config file auto save location:

```
Documents\NDI_PTZ_Controller\ndi_ptz_controller_config.json
```

* Stores:

  * Camera source names
  * Preset labels
  * Global preset labels

---

## Notes

* On first launch, NDI sources may not be detected because of the `Windows network access permission` popup.  
* Please allow network access, then restart the application.
* Some cameras may take a few seconds after connection before PTZ becomes available
* If preview does not appear immediately, wait briefly for the stream to initialize
* For best performance, use wired network connections  
  (Each NDI camera uses approximately 50 Mbps of network bandwidth)

---
<img width="918" height="712" alt="PTZ01" src="https://github.com/user-attachments/assets/b7756d67-b146-4872-a760-5e1b7d309fab" />

---

# NDI PTZ Controller
```
 이 앱을 처음 실행할때 서명되지 않은 앱으로 경고가 뜰 수 있습니다.  
 서명 정보가 포함된 앱은 MS스토어에서 받으실 수 있습니다.
```
<a href="https://get.microsoft.com/installer/download/9p0kjgjbfhnp?referrer=appbadge" target="_self" >
	<img src="https://get.microsoft.com/images/en-us%20dark.svg" width="200"/>
</a>

https://apps.microsoft.com/detail/9P0KJGJBFHNP

## 개요

NDI PTZ Controller는 NDI 기반 PTZ 카메라를 실시간으로 제어하기 위한 윈도우즈 앱입니다.
카메라 선택, PTZ 제어, 프리셋 관리, 실시간 프리뷰 기능을 하나의 인터페이스에서 제공합니다.

---

## 주요 기능

* 최대 4대의 NDI PTZ 카메라 제어
* 키보드를 이용한 실시간 PTZ 제어
* 프리셋 호출 및 저장 (1–8번 키)
* 카메라별 프리셋 이름 사용자 정의
* 전체 카메라 동시 프리셋 제어
* 앱 내부 저지연 NDI 프리뷰
* 설정 기반 자동 카메라 재연결
* OSC 제어 지원
* 설정 파일 자동 저장 및 복원
* NDI Studio Monitor 실행 기능
* NDI 멀티뷰 팝업 윈도우

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

* 설정파일 자동 저장 위치:

```
문서\NDI_PTZ_Controller\ndi_ptz_controller_config.json
```

* 저장 항목:

  * 카메라 소스 정보
  * 프리셋 이름
  * 전체 프리셋 이름

---

## 참고 사항

* 앱을 처음 실행할 때 `Windows 네트워크 액세스 허용` 팝업으로 인해 NDI 소스가 검색되지 않을 수 있습니다  
* 이 경우 네트워크 액세스를 허용한 후 앱을 종료하고 다시 실행해주세요  
* 일부 카메라는 연결 후 PTZ 제어가 활성화되기까지 몇 초가 걸릴 수 있습니다
* 프리뷰가 바로 표시되지 않으면 잠시 대기하세요
* 안정적인 사용을 위해 유선 네트워크를 권장합니다  
  (NDI 카메라 1대당 약 50Mbps의 네트워크 대역폭을 사용합니다)

---

