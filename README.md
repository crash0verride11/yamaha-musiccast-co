# crash0verride Edition (Why?)

This is a fork of the core component to incorporate my own fixes and those of others in the upstream aiomusiccast library, which seems abandoned.

## AI Transparency
Within the last year I've more heavily used AI to work on this integration. I'm a code-savvy, python-literate amateur who knows enough to spot when Claude is being a complete idiot, writing some convoluted insanity, or just making bad judgment calls. I review the code committed, excluding tests, where I only guide it to keep them practical instead of exhaustive. I try to add a human touch to the release notes for changes or features I considered, investigated, tested, captured traffic for, and spent time on. I let AI write some of the more tedious fix notes and backports from other forks, making sure appropriate credit is added. AI is not where I started, but I wouldn't have had the time to keep this project up without it.

## Added Feature List
- Actual volume
- Zone scenes
- Speaker pattern
- Surround AI
- Media player device class and icon
- Longer request timeout

### Actual Volume

I used the YXC integration as an example to incorporate a db based volume slider, that should be disabled by default, as this more directly correlates with the way the receiver is used than a percent value.

Added as a number entity per zone, in dB, with the range and step reported by the device. It's disabled by default; enable it from the entity settings.

### Zone Scenes

For zones that support scenes, two entities are added to the zone's device:
- **Scene list** (select): lists the zone's scenes as `<number>: <name>`, as named on the device. Choosing a scene only stores it; it doesn't switch anything yet. The first scene is selected at startup.
- **Switch Scene** (button): recalls the scene chosen in Scene list.

### Speaker Pattern

A select entity (configuration, device level) to switch between the speaker patterns the device supports, shown as Pattern 1, Pattern 2, and so on.

### Surround AI

A switch entity (configuration, zone level) to turn Surround:AI on or off, on devices that support it.

### Media Player Device Class and Icon

The media player's device class and icon follow the device category reported by the device:
- AV and stereo receivers: receiver device class, `mdi:audio-video` icon
- Soundbars, subwoofers, mini systems and desktop audio: speaker device class, `mdi:speaker` icon

### Longer Request Timeout

HTTP requests to the device time out after 8 seconds instead of 5.

# Setup

## Requirements

- Home Assistant 2026.11.0 or newer
- [HACS](https://hacs.xyz/), for the recommended installation

## Installation

This integration uses the same `yamaha_musiccast` domain as the built-in MusicCast integration, so Home Assistant loads it instead of the built-in one and logs a warning that a core integration is being overridden. Existing MusicCast devices and entities carry over. To go back to the built-in integration, remove this one and restart Home Assistant.

### HACS

[![Open your Home Assistant instance and open a repository inside the Home Assistant Community Store.](https://my.home-assistant.io/badges/hacs_repository.svg)](https://my.home-assistant.io/redirect/hacs_repository/?owner=crash0verride11&repository=yamaha-musiccast-co&category=integration)

The button opens this repository in HACS; download it there and restart Home Assistant. To add it by hand instead:

1. In HACS, open the menu in the top right corner and select **Custom repositories**.
2. Add `https://github.com/crash0verride11/yamaha-musiccast-co` with the type **Integration**.
3. Search for **MusicCast** in HACS and download it.
4. Restart Home Assistant.

### Manual

1. Copy `custom_components/yamaha_musiccast` from this repository into the `custom_components` folder of your Home Assistant configuration directory.
2. Restart Home Assistant.

# Usage

For everything else about using the integration (grouping, playing media, presets, and the full list of entities from the built-in integration), see the [official Home Assistant MusicCast documentation](https://www.home-assistant.io/integrations/yamaha_musiccast/). The features listed above under [Added Feature List](#added-feature-list) are specific to this edition.

> The Configuration and Troubleshooting sections below are adapted from the [Home Assistant MusicCast documentation](https://www.home-assistant.io/integrations/yamaha_musiccast/), licensed under [CC BY-NC-SA 4.0](https://creativecommons.org/licenses/by-nc-sa/4.0/). Changes: converted from the Home Assistant docs site's template syntax to plain Markdown.

## Configuration

To add the **MusicCast** device to your Home Assistant instance, use this My button:

[![Open your Home Assistant instance and start setting up a new integration.](https://my.home-assistant.io/badges/config_flow_start.svg)](https://my.home-assistant.io/redirect/config_flow_start/?domain=yamaha_musiccast)

MusicCast can be auto-discovered by Home Assistant. If an instance was found,
it will be shown as **Discovered**. You can then set it up right away.

<details>
<summary>Manual configuration steps</summary>

If it wasn't discovered automatically, don't worry! You can set up a
manual integration entry:

- Browse to your Home Assistant instance.
- Go to **[Settings > Devices & services](https://my.home-assistant.io/redirect/integrations/)**.
- In the bottom right corner, select the
  **[Add Integration](https://my.home-assistant.io/redirect/config_flow_start/?domain=yamaha_musiccast)** button.
- From the list, select **MusicCast**.
- Follow the instructions on screen to complete the setup.

</details>

## Troubleshooting

In this section known problems and their resolution are documented.

### Errors on handling UDP messages

The Yamaha MusicCast integration is working with updates sent from the device to Home Assistant instead of pulling all information every few seconds. There is no error correction mechanism in these messages, so that only 100% correct messages can be processed. Whenever there is a corrupt message the Yamaha MusicCast integration will update all device information and log an error message like these:
- `Received invalid message: <message>`
- `Received non UTF-8 compliant message: b'<binary>'`

If you receive these errors frequently, you should first try to disconnect your MusicCast devices from the power, wait 30 seconds and reconnect them to the power. If this does not help, you can try to use a LAN cable instead of WiFi to connect the device to the network.
