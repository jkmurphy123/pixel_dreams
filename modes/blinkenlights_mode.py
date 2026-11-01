import math
import random
import time

import pygame


class BlinkenlightsPanelMode:
    """
    Scene-style blinkenlights panel.

    Backward compatible with the original config, with optional extras:
      - subtitle
      - ticker_text
      - panel_id
      - status_labels
      - frame_rgb
      - label_rgb
      - panel_fill_rgb
      - title_font_scale
      - label_font_scale
      - label_font_row_fill
      - led_radius_scale
      - status_probability_per_sec
      - row_group_size
    """

    #: Fallback register names, used only when the config names none. Long enough to fill a
    #: two-column, sixteen-row panel without repeating a label.
    DEFAULT_REGISTER_LABELS = (
        "CLK", "IPTR", "ACC", "IR", "SP", "TMP",
        "MAR", "MDR", "PC", "FLAG", "ALU", "MMIO",
        "SCL", "VECT", "HOLD", "PAGE", "SEMA", "EXEC",
        "FLGS", "IO", "ACT", "NODE", "SYNC", "CTRL",
        "PIPE", "ADDR", "DATA", "BANK", "STEP", "WAIT",
        "TEST", "MASK",
    )

    def __init__(self, config: dict):
        self.computer_name = config.get("computer_name", "UNKNOWN SYSTEM")
        self.subtitle = str(config.get("subtitle", "")).strip()
        self.ticker_text = str(config.get("ticker_text", "NO FAULTS // STANDBY")).strip()
        self.panel_id = str(config.get("panel_id", "PANEL A")).strip()

        self.columns = max(1, int(config.get("columns", 2)))
        self.registers_per_column = max(1, int(config.get("registers_per_column", 6)))

        # The grid is the source of truth: `columns * registers_per_column` registers are drawn,
        # and the label list only NAMES them. Iterating the labels instead (the original shape)
        # meant a 12-name list could never fill two columns of 16 — the extra rows stayed blank
        # and the second column drew empty, whatever `columns` said.
        self.register_slots = self.columns * self.registers_per_column
        self.register_labels = [str(lbl).strip() for lbl in config.get("register_labels", [])
                                if str(lbl).strip()] or list(self.DEFAULT_REGISTER_LABELS)
        self._slot_labels = self._build_slot_labels()

        self.status_labels = list(config.get("status_labels", [])) or [
            "RUN", "MEM", "I/O", "TAPE", "SYNC", "CHK"
        ]

        self.title_font_scale = float(config.get("title_font_scale", 0.10))
        self.label_font_scale = float(config.get("label_font_scale", 0.045))
        # A label may not be taller than the row it sits in, or it draws over its neighbours.
        # This is the fraction of the row height a label's glyph size may reach; DejaVu's capitals
        # are ~0.73 of the requested size, so 1.2 fills a row edge to edge without the glyphs
        # touching. 0 would disable the cap, which is only sane on a sparse grid.
        self.label_font_row_fill = min(2.0, max(0.2, float(
            config.get("label_font_row_fill", 1.2))))
        self.led_radius_scale = float(config.get("led_radius_scale", 0.018))
        #: Caption size on the RUN/MEM/... status lamps. Separate from `label_font_scale` (the
        #: register labels) and from the panel-ID/footer type, so growing one does not drag the
        #: others along. Default matches the type these captions had before they were tunable.
        self.status_font_scale = float(config.get("status_font_scale", 0.015))
        self.pulse_speed = float(config.get("pulse_speed", 0.6))
        self.status_probability_per_sec = float(config.get("status_probability_per_sec", 0.65))
        self.row_group_size = max(0, int(config.get("row_group_size", 0)))

        self.led_color = str(config.get("led_color", "Red")).strip()
        self.frame_rgb = tuple(config.get("frame_rgb", [208, 208, 198]))
        self.label_rgb = tuple(config.get("label_rgb", [220, 220, 220]))
        self.panel_fill_rgb = tuple(config.get("panel_fill_rgb", [12, 12, 12]))
        self._led_on_base = (255, 40, 40)
        self._led_off = (60, 0, 0)

        self.burst_probability_per_sec = float(config.get("burst_probability_per_sec", 0.18))
        self.burst_duration_range = config.get("burst_duration_range", [0.6, 1.4])
        self.burst_registers_range = config.get("burst_registers_range", [1, 3])
        self.burst_strength = float(config.get("burst_strength", 1.8))

        self.title_gap_shrink = float(config.get("title_gap_shrink", 0.35))
        self.col_pad_scale = float(config.get("col_pad_scale", 0.02))
        self.border_thickness = int(config.get("border_thickness", 2))

        self.manager = None
        self.w = 0
        self.h = 0
        self.t0 = 0.0

        self._phases = [
            random.uniform(0, math.tau)
            for _ in range(self.register_slots * 8)
        ]
        self._register_bias = [random.uniform(0.75, 1.25) for _ in range(self.register_slots)]
        self._status_states = [random.random() > 0.45 for _ in range(len(self.status_labels))]
        self._status_phases = [random.uniform(0, math.tau) for _ in range(len(self.status_labels))]

        self._burst_active_until = 0.0
        self._burst_register_set = set()
        self._burst_mode = "sparkle"
        self._burst_walk_pos = 0

        self._title_font_px = 0
        self._subtitle_font_px = 0
        self._label_font_px = 0
        self._tiny_font_px = 0
        self._led_radius = 0
        self._label_width_key = None
        self._label_max_w = 0
        self._status_font_key = None
        self._status_font_used = None
        #: Rendered label surfaces, keyed by (text, px, colour) — static, so rendered once.
        self._label_cache = {}
        #: Lamp halos, keyed by (radius, quantised colour). Building a Surface per dot per frame
        #: is what costs a 32-register panel its frame rate, and the halo is a 17%-alpha disc:
        #: quantising its colour by 8 leaves no visible difference and keeps the cache small.
        self._glow_cache = {}
        #: The composed still layer (chrome, labels, footer) and the key it was built for.
        self._static = None
        self._static_key = None

    def _build_slot_labels(self) -> list:
        """
        One label per register SLOT, column-major (`idx // registers_per_column`).

        A short `register_labels` list is padded rather than truncated: the grid decides how many
        registers exist, so a profile that names 12 of 32 registers still shows a full panel with
        the unnamed rows tagged `R12`, `R13`, ... instead of leaving half the wall dark.
        """
        labels = []
        for idx in range(self.register_slots):
            labels.append(self.register_labels[idx] if idx < len(self.register_labels)
                          else f"R{idx:02d}")
        return labels

    def _label_width(self, label_font, label_px: int) -> int:
        """Widest label in `label_font`, cached per (font size, label set) — measured once."""
        key = (label_px, tuple(self._slot_labels))
        if key != self._label_width_key:
            self._label_max_w = max((label_font.size(lbl)[0] for lbl in self._slot_labels),
                                    default=0)
            self._label_width_key = key
        return self._label_max_w

    def _label_px_for_row(self, row_height: int) -> int:
        """
        The label font size actually used: the requested size, capped by the row it sits in.

        `label_font_scale` alone can ask for more than the panel can hold — 3x on a 16-row panel
        is ~97 px of type in an 81 px row, and uncapped the glyphs draw over the register above.
        The cap is expressed as a fraction of the row height (`label_font_row_fill`), so the same
        config behaves on any display size.
        """
        ceiling = int(row_height * self.label_font_row_fill)
        if ceiling <= 0:
            return self._label_font_px
        return max(10, min(self._label_font_px, ceiling))

    def _fit_leds(self, avail: int, radius: int) -> tuple:
        """
        (dot radius, centre spacing) for a bit row with `avail` pixels to spend.

        Spacing tightens first, and never below 2.15 radii — below that the eight dots merge into
        one bar — and only then do the dots themselves shrink. So a label that grew to fill its
        row squeezes the bit row instead of being drawn over by it.
        """
        dot_r = max(2, int(radius))
        if avail < (7 * 2.55 + 2) * dot_r:
            dot_r = max(2, int(avail / (7 * 2.55 + 2)))
        spacing = (avail - 2 * dot_r) // 7
        spacing = max(int(dot_r * 2.15), min(int(dot_r * 2.55), spacing))
        return dot_r, spacing

    def _label_surface(self, label_font, label: str, label_px: int, color):
        """
        The rendered label, cached: a register label never changes, so re-rendering 32 of them on
        every frame is pure waste (measured as most of the cost of a second column).
        """
        key = (label, label_px, color)
        surf = self._label_cache.get(key)
        if surf is None:
            if len(self._label_cache) > 256:
                self._label_cache.clear()
            surf = label_font.render(label, True, color)
            self._label_cache[key] = surf
        return surf

    def _glow_sprite(self, radius: int, color) -> tuple:
        """
        (surface, half-width) for a lamp halo — built once per (radius, quantised colour).

        `color` varies continuously with the pulse, so it is quantised by 8 for the cache key: the
        halo is drawn at alpha 44 and the steps are invisible, while an unquantised key would miss
        on nearly every dot and rebuild a surface 256 times a frame.
        """
        key = (radius, (color[0] & 0xF8, color[1] & 0xF8, color[2] & 0xF8))
        surf = self._glow_cache.get(key)
        if surf is None:
            if len(self._glow_cache) > 256:
                self._glow_cache.clear()
            glow_r = radius + max(2, radius // 2)
            surf = pygame.Surface((glow_r * 2 + 4, glow_r * 2 + 4), pygame.SRCALPHA)
            pygame.draw.circle(surf, (*key[1], 44), (glow_r + 2, glow_r + 2), glow_r)
            self._glow_cache[key] = surf
        return surf, surf.get_width() // 2

    def _status_font(self, lamp_w: int, lamp_h: int) -> tuple:
        """
        (font, px) for the status lamp captions — `status_font_scale`, capped by the lamp itself.

        A caption is drawn INSIDE its lamp, so a size the lamp cannot hold spills over the
        neighbour: cap at the lamp height first (DejaVu's capitals are ~0.73 of the requested
        size), then shrink once more if the longest caption is wider than the lamp. Both limits
        are measured off the caption set and the geometry, so they follow a resized screen.
        """
        px = max(10, min(self._status_font_px, int(lamp_h * 0.78)))
        key = (px, lamp_w, tuple(self.status_labels))
        if key == self._status_font_key and self._status_font_used is not None:
            return self._status_font_used
        font = self.manager.cache.get_font("dejavusansmono", px, bold=False)
        widest = max((font.size(lbl)[0] for lbl in self.status_labels), default=0)
        if widest > max(1, lamp_w - 12):
            px = max(10, int(px * (lamp_w - 12) / widest))
            font = self.manager.cache.get_font("dejavusansmono", px, bold=False)
        self._status_font_key = key
        self._status_font_used = (font, px)
        return self._status_font_used

    def _panel_geometry(self) -> dict:
        """
        The panel's rects and cell sizes — the ONE place the layout arithmetic lives, so render()
        and the tests that measure the drawn frame agree on where a column/row actually is.
        """
        w, h = self.w, self.h
        header_h = max(64, int(h * 0.12))
        footer_h = max(42, int(h * 0.07))
        outer_pad = int(min(w, h) * 0.035)
        status_h = max(38, int(h * 0.075))

        header_rect = pygame.Rect(outer_pad, outer_pad, w - outer_pad * 2, header_h)
        status_rect = pygame.Rect(outer_pad, header_rect.bottom + 8, w - outer_pad * 2, status_h)
        panel_rect = pygame.Rect(
            outer_pad,
            status_rect.bottom + 10,
            w - outer_pad * 2,
            h - outer_pad - footer_h - (status_rect.bottom + 10),
        )
        footer_rect = pygame.Rect(outer_pad, h - outer_pad - footer_h, w - outer_pad * 2, footer_h)
        inner_rect = panel_rect.inflate(-18, -18)
        return {
            "header": header_rect,
            "status": status_rect,
            "panel": panel_rect,
            "footer": footer_rect,
            "inner": inner_rect,
            "col_pad": int(panel_rect.width * self.col_pad_scale),
            "col_width": max(1, inner_rect.width // max(1, self.columns)),
            "row_height": max(1, inner_rect.height // max(1, self.registers_per_column)),
        }

    def _resolve_led_colors(self):
        name = (self.led_color or "Red").strip().lower()
        palette = {
            "red": (255, 40, 40),
            "orange": (255, 140, 40),
            "yellow": (255, 230, 60),
            "green": (70, 255, 110),
            "blue": (80, 170, 255),
            "purple": (180, 90, 255),
            "pink": (255, 90, 190),
            "white": (245, 245, 245),
            "amber": (255, 176, 64),
        }
        on = palette.get(name, palette["red"])
        off = (
            max(10, int(on[0] * 0.18)),
            max(10, int(on[1] * 0.18)),
            max(10, int(on[2] * 0.18)),
        )
        self._led_on_base = on
        self._led_off = off

    def enter(self, manager):
        self.manager = manager
        self.w, self.h = manager.screen.get_size()
        self.t0 = time.time()
        self._recompute_scaled_metrics()
        self._resolve_led_colors()

    def exit(self):
        # The composed static layer is a full-screen surface: drop it (and the sprite caches)
        # so the next mode inherits no memory.
        self._static = None
        self._static_key = None
        self._label_cache.clear()
        self._glow_cache.clear()
        self.manager = None

    def handle_event(self, event):
        pass

    def update(self, dt: float):
        now = time.time()

        if now >= self._burst_active_until:
            if random.random() < (self.burst_probability_per_sec * dt):
                self._start_burst(now)

        if now < self._burst_active_until and self._burst_mode == "walk":
            if int((now * 1000) / 90) != int(((now - dt) * 1000) / 90):
                self._burst_walk_pos = (self._burst_walk_pos + 1) % 8

        for idx in range(len(self._status_states)):
            if random.random() < self.status_probability_per_sec * dt * 0.25:
                self._status_states[idx] = not self._status_states[idx]
            self._status_phases[idx] += dt * random.uniform(0.8, 1.6)

        w2, h2 = self.manager.screen.get_size()
        if (w2, h2) != (self.w, self.h):
            self.w, self.h = w2, h2
            self._recompute_scaled_metrics()

    def render(self, screen: pygame.Surface):
        led_off = self._led_off
        led_on_base = self._led_on_base

        tiny_font = self.manager.cache.get_font("dejavusansmono", self._tiny_font_px, bold=False)
        geo = self._panel_geometry()
        inner_rect = geo["inner"]
        col_pad = geo["col_pad"]
        col_width = geo["col_width"]
        row_height = geo["row_height"]
        label_px = self._label_px_for_row(row_height)
        label_font = self.manager.cache.get_font("dejavusansmono", label_px, bold=False)
        label_max_w = self._label_width(label_font, label_px)

        # Everything that does not move — chrome, the register labels, the footer text — is
        # composed ONCE and blitted. Drawing it every frame cost 10 of this mode's 13 ms on the
        # wall (a 2x16 panel means 32 label blits of 97 px type, measured), which is what a
        # tripled label size turned into a frame-rate drop.
        screen.blit(self._static_layer(geo, label_font, label_px, tiny_font), (0, 0))
        self._draw_status_lamps(screen, geo["status"])

        led_radius = self._led_radius
        label_gap = max(led_radius + 6, int(col_width * 0.02))
        right_inset = max(1, col_pad // 2)

        now = time.time()
        t = now - self.t0
        phase_idx = 0

        for idx in range(self.register_slots):
            col = idx // self.registers_per_column
            row = idx % self.registers_per_column

            col_left = inner_rect.left + col * col_width
            inner_left = col_left + col_pad
            inner_right = col_left + col_width - col_pad
            cy = inner_rect.top + row * row_height + (row_height // 2)

            # The bit row gets whatever width is left after the WIDEST label in the panel.
            avail = (inner_right - inner_left) - label_max_w - label_gap
            dot_r, led_spacing = self._fit_leds(avail, led_radius)
            leds_total_w = 7 * led_spacing + 2 * dot_r
            leds_x = inner_right - right_inset - leds_total_w
            leds_x = max(leds_x, inner_left + label_max_w + label_gap)

            is_burst_reg = now < self._burst_active_until and idx in self._burst_register_set
            reg_bias = self._register_bias[idx % len(self._register_bias)]

            for bit in range(8):
                phase = self._phases[phase_idx]
                phase_idx += 1

                base_wave = (math.sin(t * self.pulse_speed + phase) + 1.0) / 2.0
                secondary = (math.sin(t * (self.pulse_speed * 0.45) + phase * 1.8 + idx * 0.2) + 1.0) / 2.0
                intensity = (0.08 + 0.72 * base_wave + 0.20 * secondary) * reg_bias

                if is_burst_reg:
                    if self._burst_mode == "sparkle":
                        flick = (math.sin(t * 9.0 + phase * 3.0) + 1.0) / 2.0
                        intensity *= (1.0 + 1.05 * flick) * self.burst_strength
                    else:
                        intensity *= 1.0 + 0.45 * ((math.sin(t * 6.0 + phase) + 1.0) / 2.0)
                        if bit == self._burst_walk_pos:
                            intensity *= 2.4 * self.burst_strength

                intensity = max(0.0, min(2.6, intensity))
                color = (
                    int(min(255, led_on_base[0] * intensity)),
                    int(min(255, led_on_base[1] * intensity)),
                    int(min(255, led_on_base[2] * intensity)),
                )

                cx = leds_x + bit * led_spacing
                self._draw_led(screen, cx, cy, dot_r, color, led_off)

    def _static_layer(self, geo: dict, label_font, label_px: int,
                      tiny_font) -> pygame.Surface:
        """
        The chrome, the column boxes, the register labels and the footer text, drawn once.

        Nothing in here changes while the mode is on screen — the lamps and the status lights are
        the only moving parts — so it is composed into one surface and blitted each frame. The key
        covers the screen size and everything that feeds the drawing, so a resize or a rebuilt
        mode re-composes it rather than blitting a stale panel.
        """
        key = (self.w, self.h, label_px, tuple(self._slot_labels), self.frame_rgb,
               self.panel_fill_rgb, self.label_rgb, self.computer_name, self.subtitle,
               self.panel_id, self.ticker_text, self.border_thickness, self.row_group_size,
               self.columns, self.registers_per_column)
        if self._static_key == key and self._static is not None:
            return self._static

        label_color = self.label_rgb
        border_color = self.frame_rgb
        border_thickness = max(1, self.border_thickness)
        inner_rect = geo["inner"]
        col_pad = geo["col_pad"]
        col_width = geo["col_width"]
        row_height = geo["row_height"]

        surf = pygame.Surface((self.w, self.h))
        surf.fill((4, 4, 4))

        for rect in (geo["header"], geo["status"], geo["panel"], geo["footer"]):
            pygame.draw.rect(surf, self.panel_fill_rgb, rect)
            pygame.draw.rect(surf, border_color, rect, border_thickness)

        title_font = self.manager.cache.get_font("dejavusansmono", self._title_font_px, bold=True)
        subtitle_font = self.manager.cache.get_font("dejavusansmono", self._subtitle_font_px, bold=False)
        header_rect = geo["header"]
        title_surf = title_font.render(self.computer_name, True, label_color)
        surf.blit(title_surf, (header_rect.left + 18, header_rect.top + 12))
        if self.subtitle:
            subtitle_surf = subtitle_font.render(self.subtitle, True, border_color)
            surf.blit(subtitle_surf, (header_rect.left + 20,
                                      title_surf.get_rect().bottom + header_rect.top + 8))

        panel_id_surf = tiny_font.render(self.panel_id, True, border_color)
        surf.blit(panel_id_surf, (header_rect.right - panel_id_surf.get_width() - 16,
                                  header_rect.top + 12))

        for c in range(self.columns):
            x0 = inner_rect.left + c * col_width + col_pad // 2
            rect = pygame.Rect(x0, inner_rect.top, col_width - col_pad, inner_rect.height)
            pygame.draw.rect(surf, (16, 16, 16), rect)
            pygame.draw.rect(surf, border_color, rect, border_thickness)

            if c < self.columns - 1:
                bus_x = rect.right + (col_pad // 2)
                pygame.draw.line(surf, border_color, (bus_x, rect.top + 16),
                                 (bus_x, rect.bottom - 16), 1)

        for idx in range(self.register_slots):
            col = idx // self.registers_per_column
            row = idx % self.registers_per_column
            col_left = inner_rect.left + col * col_width
            inner_left = col_left + col_pad
            inner_right = col_left + col_width - col_pad
            y = inner_rect.top + row * row_height

            if self.row_group_size and row > 0 and (row % self.row_group_size == 0):
                sep_y = y - max(2, row_height // 10)
                pygame.draw.line(surf, border_color, (col_left + 10, sep_y),
                                 (col_left + col_width - 10, sep_y), 1)

            label_surf = self._label_surface(label_font, self._slot_labels[idx], label_px,
                                             label_color)
            surf.blit(label_surf, (inner_left, y + (row_height // 2) - label_surf.get_height() // 2))

        footer_rect = geo["footer"]
        footer_left = tiny_font.render("ACTIVITY BUS", True, border_color)
        ticker = tiny_font.render(self.ticker_text, True, label_color)
        surf.blit(footer_left, (footer_rect.left + 14, footer_rect.top + 12))
        surf.blit(ticker, (footer_rect.right - ticker.get_width() - 14, footer_rect.top + 12))

        self._static = surf
        self._static_key = key
        return surf

    def _draw_led(self, screen, cx: int, cy: int, radius: int, color, off_color):
        glow, half = self._glow_sprite(radius, color)
        screen.blit(glow, (cx - half, cy - half))
        pygame.draw.circle(screen, color, (cx, cy), radius)
        pygame.draw.circle(screen, off_color, (cx, cy), radius, 1)

    def _draw_status_lamps(self, screen, rect: pygame.Rect):
        lamp_count = max(1, len(self.status_labels))
        gap = max(10, rect.width // (lamp_count * 10))
        total_gap = gap * (lamp_count - 1)
        lamp_w = max(36, (rect.width - 24 - total_gap) // lamp_count)
        lamp_h = max(18, rect.height - 18)
        x = rect.left + 12
        y = rect.top + (rect.height - lamp_h) // 2
        status_font, status_px = self._status_font(lamp_w, lamp_h)

        for idx, label in enumerate(self.status_labels):
            lamp_rect = pygame.Rect(x, y, lamp_w, lamp_h)
            state = self._status_states[idx]
            pulse = 0.65 + 0.35 * math.sin(self._status_phases[idx])
            on = self._led_on_base if state else self._led_off
            fill = (
                min(255, int(on[0] * (pulse if state else 0.55))),
                min(255, int(on[1] * (pulse if state else 0.55))),
                min(255, int(on[2] * (pulse if state else 0.55))),
            )

            pygame.draw.rect(screen, fill, lamp_rect, border_radius=3)
            pygame.draw.rect(screen, self.frame_rgb, lamp_rect, 1, border_radius=3)
            surf = self._label_surface(status_font, label, status_px,
                                       (10, 10, 10) if state else self.label_rgb)
            screen.blit(
                surf,
                (
                    lamp_rect.centerx - surf.get_width() // 2,
                    lamp_rect.centery - surf.get_height() // 2,
                ),
            )
            x += lamp_w + gap

    def _recompute_scaled_metrics(self):
        base = min(self.w, self.h)
        self._title_font_px = max(22, int(base * self.title_font_scale))
        self._subtitle_font_px = max(11, int(base * 0.020))
        self._label_font_px = max(11, int(base * self.label_font_scale))
        self._status_font_px = max(10, int(base * self.status_font_scale))
        self._tiny_font_px = max(10, int(base * 0.015))
        self._led_radius = max(5, int(base * self.led_radius_scale))

    def _start_burst(self, now: float):
        dur = random.uniform(float(self.burst_duration_range[0]), float(self.burst_duration_range[1]))
        n_regs = random.randint(int(self.burst_registers_range[0]), int(self.burst_registers_range[1]))
        n_regs = max(1, min(n_regs, self.register_slots))
        self._burst_register_set = set(random.sample(range(self.register_slots), n_regs))
        self._burst_active_until = now + dur
        self._burst_mode = random.choice(["sparkle", "walk"])
        self._burst_walk_pos = random.randint(0, 7)
