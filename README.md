# Christie Griffyn for Home Assistant

A local-polling custom integration for Christie Griffyn laser projectors. It was written for the Griffyn 4K35-RGB and tested on firmware 1.3.7.

It talks to the projector over TCP port 3002 with Christie's TruLife+ serial protocol, the `(CODE …)` commands documented in the *TruLife+ Serial API Commands* reference (020-103316-13) and *Status System* reference (020-103327-17). Other TruLife+ projectors (Eclipse, M RGB, Sapphire) speak the same protocol and will probably work, but they have not been tested. You add the integration by entering the projector's IP address. Nothing in this repository is specific to one installation.

## Entities

Settings the projector rejects or does not report are left out or shown as unavailable. Lists such as inputs, profiles and test patterns are read from the projector, so the choices match yours.

- **Power** switch. The **Power state** sensor shows `standby`, `warming_up`, `on` or `cooling_down`.
- **Switches:** shutter open, freeze image, on-screen display, RealBlack, stealth mode, camera-friendly color, enhanced DMD healing, auto power on, keep electronics on in standby, film mode detect, video thumbnails, lens lock, front/rear IR sensors, wired keypad, invert 3D eyes, keystone gain compensation and black level offsets. The less common ones are disabled by default.
- **Selects:** input (`CHA`, the channel list), input slot and port configuration, profile, test pattern, engine test pattern, LiteLOC, fan profile, gamma function, color space, resize, 3D mode and sync out, warp, edge blend, black level blend, color enable, EDID frame rate, screen orientation, splash color, menu position and language, Christie Link input, SDI payload and temperature units.
- **Numbers:** laser power (%), red/green/blue laser drive, white point x/y, sharpness, gamma, maximum/minimum luminance, PQ white level, frame delay, RealBlack delay and threshold. Lens horizontal, vertical, zoom and focus take their limits from the projector and are disabled by default, because moving them changes the picture framing.
- **Buttons:** refresh, calibrate lens and lens home.
- **Sensors:** laser hours, laser standby hours, laser on cycles, projector hours, diffuser hours, light source state, LiteLOC status, and the incoming signal (description, resolution, frame rate, color format, bit depth, dynamic range, output frequency, frame delay time). Every temperature and fan the projector reports gets its own sensor; the main ones are on by default and the rest are disabled. Temperatures are converted to °C, and Home Assistant shows them in your unit system. Diagnostic sensors cover inlet voltage, power supply current, diffuser speed, pitch/roll, laser CPU temperature and the last unsolicited message.
- **Status** sensor (`ok`, `warning` or `error`) and a **Problem** binary sensor. Any status item the projector flags is listed in the `problems` attribute. Binary sensors also show whether a signal is present and frame-locked.

### Profiles

The projector can recall a profile but cannot report which one is active. The Profile select shows the last profile chosen from Home Assistant, and keeps it across restarts.

### Raw commands

The `christie_griffyn.send_command` action sends any protocol command and returns the projector's replies:

```yaml
action: christie_griffyn.send_command
data:
  command: "SST+TEMP?"
response_variable: result
```

Queries (anything with `?`) return the projector's replies. Other commands are sent with an acknowledgement request, and failures are raised as errors. If more than one projector is set up, add `config_entry_id`.

Unsolicited messages, such as errors or FYI messages the projector sends on its own, fire a `christie_griffyn_message` event.

## Install with HACS

This is not in the default HACS catalog. Add it as a custom repository:

1. In Home Assistant, open **HACS**.
2. Open the three-dot menu and choose **Custom repositories**.
3. Repository URL: `https://github.com/johncarey70/ha-christie-griffyn`
4. Category: **Integration**.
5. Add the repository, then find **Christie Griffyn** in HACS and download it.
6. Restart Home Assistant.
7. Go to **Settings → Devices & services → Add integration**, choose **Christie Griffyn**, and enter the projector's IP address (port 3002).

Home Assistant must be able to reach the projector on TCP port 3002. Minimum Home Assistant version is 2025.2.0.

Manual install is also possible: copy `custom_components/christie_griffyn` into `/config/custom_components/` and restart.

## Care with the projector

- The integration keeps one TCP connection open, sends one command at a time, and reconnects on its own if the connection drops.
- Power, shutter, input and signal are read every 30 seconds by default (10–600 seconds, changeable under **Configure**). Settings and status are read every fourth poll. Lists and the model/firmware are read at start-up and after each power change.
- In standby the projector answers fewer queries. Those entities become unavailable until it is back on.
- Power on and off are sent without waiting for an acknowledgement, because the projector can take more than 20 seconds to respond while it warms up.

## Protocol reference

- [TruLife+ Serial API Commands (020-103316-13)](https://www.christiedigital.com/globalassets/resources/public/020-103316-13-Christie-LIT-TECH-REF-TruLifePlus-API.pdf)
- [TruLife+ Status System (020-103327-17)](https://www.christiedigital.com/globalassets/resources/public/020-103327-17-Christie-LIT-TECH-REF-TruLifePlus-STATSYS.pdf)
- [TruLife+ LAS command bulletin (020-200567-01)](https://www.christiedigital.com/globalassets/resources/public/020-200567-01-christie-bul-tech-trulife-las-cmd.pdf)

Christie and Griffyn are trademarks of Christie Digital Systems. This project is not affiliated with or endorsed by Christie. The icon in `brand/` is Christie's logo mark.

## Development

```sh
pip install -r requirements_test.txt
pytest
```

The tests run against a fake projector that plays back replies recorded from a real Griffyn 4K35-RGB. The address and serial numbers in them have been replaced.

## License

MIT, copyright John Carey 2026.
