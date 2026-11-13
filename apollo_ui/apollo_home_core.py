"""Native, CPU-painted Apollo core. No WebGL, video loop or GPU dependencies."""
import math
import random
import time

from PySide6.QtCore import QPointF, QRectF, QSize, Qt, QTimer, Signal, Property, QPropertyAnimation, QEasingCurve
from PySide6.QtGui import QColor, QFont, QPainter, QPainterPath, QPen, QPixmap, QRadialGradient
from PySide6.QtWidgets import QFrame, QHBoxLayout, QLabel, QPushButton, QVBoxLayout, QWidget, QCheckBox

from apollo_core_activity import CoreActivity, speech_motion_level


GREEN = "#65ff9c"
RING_DEGREES_PER_SECOND = {"idle": 5, "listening": 7, "thinking": 12,
                           "researching": 10, "working": 10, "voice": 8, "speaking": 6}


class ApolloCoreCanvas(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setMinimumHeight(280)
        self.setAccessibleName("Apollo animated activity core")
        self.activity = CoreActivity()
        self.reduced_motion = False
        self.show_side_labels = True
        self._phase = 0.0
        self._elapsed = 0.0
        self._ring_angle = 0.0
        self._last_tick = time.monotonic()
        self._level = 0.0
        self._background = None
        self.timer = QTimer(self)
        self.timer.timeout.connect(self._tick)

    def sizeHint(self):
        return QSize(780, 310)

    def copy_motion_from(self, other):
        for name in ("_phase", "_elapsed", "_ring_angle", "_level"):
            setattr(self, name, getattr(other, name))
        self.activity = other.activity
        self.update()

    def set_activity(self, activity):
        previous = self.activity
        if activity == previous:
            return
        self.activity = activity
        self.setAccessibleDescription(activity.title + ". " + activity.detail)
        self._sync_timer()
        if not self.reduced_motion or activity.state != previous.state:
            self.update()

    def set_reduced_motion(self, value):
        self.reduced_motion = bool(value)
        self._sync_timer()
        self.update()

    def _sync_timer(self):
        if self.isVisible() and not self.reduced_motion:
            interval = 80 if self.activity.state == "idle" else 40
            if not self.timer.isActive() or self.timer.interval() != interval:
                self.timer.start(interval)
        else:
            self.timer.stop()

    def showEvent(self, event):
        super().showEvent(event)
        self._last_tick = time.monotonic()
        self._sync_timer()

    def hideEvent(self, event):
        self.timer.stop()
        super().hideEvent(event)

    def _tick(self):
        if self.window().isMinimized() or self.visibleRegion().isEmpty():
            self._last_tick = time.monotonic()
            return
        now = time.monotonic()
        speed = {"idle": .22, "thinking": 1.1, "voice": .7, "researching": .85,
                 "working": .9, "listening": .45, "speaking": .6}.get(self.activity.state, .25)
        dt = max(0.0, min(.12, now - self._last_tick))
        self._phase += dt * speed
        self._elapsed += dt
        self._ring_angle = (self._ring_angle + dt * RING_DEGREES_PER_SECOND.get(self.activity.state, 5)) % 360
        self._last_tick = now
        target = speech_motion_level(self.activity.level, self._elapsed, self.activity.level_available) if self.activity.state == "speaking" else 0.0
        response = .055 if target > self._level else .09
        self._level += (target - self._level) * (1 - math.exp(-dt / response))
        self.update()

    def _galaxy(self):
        ratio = self.devicePixelRatioF()
        key = (self.width(), self.height(), ratio)
        if self._background is not None and self._background[0] == key:
            return self._background[1]
        pixmap = QPixmap(round(self.width() * ratio), round(self.height() * ratio))
        pixmap.setDevicePixelRatio(ratio)
        pixmap.fill(QColor("#020605"))
        p = QPainter(pixmap)
        p.setRenderHint(QPainter.Antialiasing)
        w, h = self.width(), self.height()
        rng = random.Random(315)
        # A cached spiral/galaxy cloud; all movement belongs to the core.
        p.save()
        p.translate(w * .5, h * .51)
        p.rotate(-23)
        p.scale(2.8, .65)
        glow = QRadialGradient(QPointF(0, 0), h * .56)
        glow.setColorAt(0, QColor(44, 131, 73, 80))
        glow.setColorAt(.32, QColor(21, 86, 46, 60))
        glow.setColorAt(.72, QColor(9, 34, 23, 24))
        glow.setColorAt(1, QColor(0, 0, 0, 0))
        p.setPen(Qt.NoPen); p.setBrush(glow)
        p.drawEllipse(QPointF(0, 0), h * .56, h * .56)
        p.restore()
        for i in range(340):
            arm = i % 2 * math.pi
            angle = i / 340 * math.tau * 1.6 + arm
            distance = 20 + i / 340 * w * .42
            x = math.cos(angle) * distance
            y = math.sin(angle) * distance * .2 + rng.gauss(0, 9)
            # Tilt the two fine star arms through the surrounding green haze.
            xx = w / 2 + x * .94 + y * .34
            yy = h / 2 - x * .34 + y * .94
            p.setPen(Qt.NoPen); p.setBrush(QColor(134, 222, 163, rng.randrange(15, 65)))
            p.drawEllipse(QPointF(xx, yy), .65, .65)
        for i in range(240):
            x, y = rng.random() * w, rng.random() * h
            bright = rng.randrange(35, 135)
            radius = rng.choice((.45, .6, .8, 1.15))
            p.setPen(Qt.NoPen); p.setBrush(QColor(165, 230, 191, bright))
            p.drawEllipse(QPointF(x, y), radius, radius)
            if i % 33 == 0:
                p.setPen(QPen(QColor(140, 255, 180, 50), .6))
                p.drawLine(QPointF(x - 3, y), QPointF(x + 3, y))
                p.drawLine(QPointF(x, y - 3), QPointF(x, y + 3))
        p.end()
        self._background = (key, pixmap)
        return pixmap

    @staticmethod
    def _circle(p, radius, color, width=1):
        p.setPen(QPen(QColor(color), width)); p.setBrush(Qt.NoBrush)
        p.drawEllipse(QPointF(0, 0), radius, radius)

    def paintEvent(self, event):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        p.drawPixmap(0, 0, self._galaxy())
        w, h = self.width(), self.height()
        t = 0.0 if self.reduced_motion else self._phase
        state = self.activity.state
        speaking = state == "speaking"
        elapsed = 0.0 if self.reduced_motion else self._elapsed
        breath = .5 + .5 * math.sin(elapsed * math.tau / 5.6)
        voice_level = self._level if speaking else 0.0
        energy = .06 + .10 * breath + .65 * voice_level
        r = min(h * .265, w * .19, 92)
        p.save(); p.translate(w / 2, h / 2 - 6)

        halo_r = r * (1.82 + .18 * breath)
        halo = QRadialGradient(QPointF(0, 0), halo_r)
        halo.setColorAt(0, QColor(39, 255, 120, 22 + int(20 * breath)))
        halo.setColorAt(.5, QColor(37, 255, 123, 12 + int(16 * breath + voice_level * 25)))
        halo.setColorAt(1, QColor(0, 0, 0, 0))
        p.setPen(Qt.NoPen); p.setBrush(halo)
        p.drawEllipse(QPointF(0, 0), halo_r, halo_r)

        for radius in (1.18, 1.38, 1.57):
            self._circle(p, r * radius, "#17432a", .8)
        for i in range(72):
            angle = i * math.tau / 72
            inner, outer = r * 1.45, r * (1.51 if i % 6 == 0 else 1.48)
            p.setPen(QPen(QColor("#44845a"), 1 if i % 6 == 0 else .5))
            p.drawLine(QPointF(math.cos(angle) * inner, math.sin(angle) * inner),
                       QPointF(math.cos(angle) * outer, math.sin(angle) * outer))
        for ring, direction in ((1.2, 1), (1.38, -1)):
            p.setPen(QPen(QColor(GREEN), 2 if ring == 1.2 else 1.1))
            for offset, length in ((0, 62), (125, 24), (224, 42)):
                angle = ((0.0 if self.reduced_motion else self._ring_angle) * direction + offset) % 360
                p.drawArc(QRectF(-r * ring, -r * ring, r * ring * 2, r * ring * 2), int(angle * 16), length * 16)

        if state == "listening":
            for offset in (0, .5):
                progress = (t * .8 + offset) % 1
                p.setPen(QPen(QColor(101, 255, 156, int((1 - progress) * 100)), 1))
                radius = r * (1.05 + progress * .7)
                p.drawEllipse(QPointF(0, 0), radius, radius)

        sphere_r = r * (.975 + .05 * breath + .025 * voice_level)
        sphere = QRadialGradient(QPointF(-r * .3, -r * .35), r * 1.5)
        sphere.setColorAt(0, QColor("#1a5633"))
        sphere.setColorAt(.5, QColor("#062519"))
        sphere.setColorAt(.72, QColor("#0a4326"))
        sphere.setColorAt(1, QColor("#020906"))
        p.setBrush(sphere); p.setPen(QPen(QColor("#56ff94"), 1.4))
        p.drawEllipse(QPointF(0, 0), sphere_r, sphere_r)
        p.save()
        clip = QPainterPath(); clip.addEllipse(QPointF(0, 0), sphere_r, sphere_r)
        p.setClipPath(clip)
        # Rotating spherical filaments, projected directly into 2D.
        for band in range(9):
            latitude = -.95 + band * .235
            path = QPainterPath()
            for j in range(85):
                longitude = j / 84 * math.tau
                tilt = latitude + .19 * math.sin(longitude * 2 + t * 2 + band * .4)
                tilt = max(-.99, min(.99, tilt))
                rr = math.sqrt(1 - tilt * tilt)
                x = math.cos(longitude + t * .6) * rr * sphere_r
                z = math.sin(longitude + t * .6) * rr
                y = (tilt * .87 + z * .36) * sphere_r
                if j == 0: path.moveTo(x, y)
                else: path.lineTo(x, y)
            p.setPen(QPen(QColor(95, 255, 151, 40 + band * 8 + int(energy * 45)), .8))
            p.drawPath(path)
        # Opposing energy waves open like abstract lips. Measured silence closes
        # them; this is an amplitude response, not a phoneme/viseme prediction.
        for side in (-1, 1):
            path = QPainterPath()
            for j in range(110):
                u = j / 109 * 2 - 1
                x = u * sphere_r * .9
                profile = max(0, 1 - u * u) ** .7
                opening = sphere_r * (.014 + .34 * voice_level)
                shape = .86 + .12 * math.cos(u * math.tau) if side < 0 else 1.1
                ripple = math.sin(u * 8 + elapsed * 15) * sphere_r * .022 * voice_level * profile
                resting_wave = math.sin(u * 3 + t * .5) * sphere_r * .018 * profile
                y = side * opening * profile * shape + ripple + resting_wave
                if j == 0: path.moveTo(x, y)
                else: path.lineTo(x, y)
            for width, alpha in ((14, 12), (7, 25), (3, 65), (1.5, 225)):
                p.setPen(QPen(QColor(105, 255, 160, alpha), width)); p.drawPath(path)
        for i in range(58):
            a = i * 2.39996 + t * .3
            distance = math.sqrt((i + .5) / 58) * sphere_r * .94
            p.setPen(Qt.NoPen); p.setBrush(QColor(176, 255, 203, 65 + i % 4 * 25))
            p.drawEllipse(QPointF(math.cos(a) * distance, math.sin(a) * distance), .8, .8)
        p.restore()
        self._circle(p, sphere_r + 3, "#277f45", .7)

        # A restrained signal trace below the globe. It animates only for voice.
        p.setPen(QPen(QColor(GREEN), 1.4))
        for i in range(35):
            x = (i - 17) * 3.5
            height = 1.2
            if speaking and not self.reduced_motion:
                height += voice_level * 22 * (.3 + .7 * abs(math.sin(i * 1.7 + elapsed * 18))) * (1 - abs(i - 17) / 20)
            p.drawLine(QPointF(x, r * 1.72 - height), QPointF(x, r * 1.72 + height))
        p.restore()

        if w > 650 and self.show_side_labels:
            p.setFont(QFont("Segoe UI", 8))
            p.setPen(QColor("#5b896b"))
            p.drawText(QRectF(22, h * .46, 160, 20), Qt.AlignLeft, "Z S S  L A B O R A T O R I E S")
            p.drawText(QRectF(w - 175, h * .46, 153, 20), Qt.AlignRight, "L O C A L  C O R E")
        p.end()


class ApolloHomeCore(QFrame):
    chat_requested = Signal()
    listen_requested = Signal()
    mute_requested = Signal()
    motion_changed = Signal(bool)

    def __init__(self, parent=None, reduced_motion=False):
        super().__init__(parent)
        self.setObjectName("apolloCore")
        self.setStyleSheet("""
            QFrame#apolloCore { background:#020605; border:1px solid #183b26; border-radius:16px; }
            QFrame#apolloCore QLabel { background:transparent; border:0; color:#8da997; }
            QFrame#apolloCore QPushButton { background:#09150e; color:#bcefd0; border:1px solid #214e32;
                border-radius:8px; padding:7px 12px; min-height:20px; }
            QFrame#apolloCore QPushButton:hover { background:#112c1b; border-color:#65ff9c; }
            QFrame#apolloCore QPushButton:focus { border:2px solid #65ff9c; }
            QFrame#apolloCore QPushButton:checked { color:#65ff9c; background:#143321; }
        """)
        layout = QVBoxLayout(self); layout.setContentsMargins(18, 14, 18, 16); layout.setSpacing(4)
        header = QHBoxLayout()
        name = QLabel("A P O L L O"); name.setStyleSheet("color:#d5ffe3;font-size:17px;font-weight:600;letter-spacing:3px")
        header.addWidget(name); header.addStretch()
        self.model = QLabel("LOCAL CORE"); self.model.setStyleSheet("font-size:10px;color:#79ac8a")
        header.addWidget(self.model)
        layout.addLayout(header)
        self.canvas = ApolloCoreCanvas(); layout.addWidget(self.canvas)
        self.title = QLabel(); self.title.setAlignment(Qt.AlignCenter)
        self.title.setStyleSheet("color:#8dffb3;font-size:19px;font-weight:600")
        self.detail = QLabel(); self.detail.setAlignment(Qt.AlignCenter); self.detail.setWordWrap(True)
        self.detail.setMinimumHeight(34)
        layout.addWidget(self.title); layout.addWidget(self.detail)
        actions = QHBoxLayout(); actions.setContentsMargins(0, 8, 0, 0)
        self.chat = QPushButton("Open chat"); self.chat.clicked.connect(self.chat_requested)
        self.listen = QPushButton("Dictate"); self.listen.clicked.connect(self.listen_requested)
        self.mute = QPushButton("Voice on"); self.mute.clicked.connect(self.mute_requested)
        self.motion = QPushButton("Reduce motion"); self.motion.setCheckable(True)
        self.motion.setToolTip("Keep the galaxy and core still while activity labels continue to update.")
        self.motion.toggled.connect(self.canvas.set_reduced_motion)
        self.motion.toggled.connect(self.motion_changed)
        self.motion.setChecked(bool(reduced_motion))
        actions.addStretch()
        for button in (self.chat, self.listen, self.mute, self.motion): actions.addWidget(button)
        actions.addStretch(); layout.addLayout(actions)
        self.set_activity(CoreActivity())

    def set_activity(self, activity):
        self.canvas.set_activity(activity)
        if self.title.text() != activity.title: self.title.setText(activity.title)
        if self.detail.text() != activity.detail: self.detail.setText(activity.detail)

    def set_voice(self, muted, available, listening=False):
        self.mute.setText("Voice muted" if muted else "Voice on")
        self.listen.setEnabled(available and not listening)
        self.listen.setText("Listening…" if listening else "Dictate")
        self.listen.setToolTip("Dictate a message, then review it in Chat before sending." if available
                               else "Enable Speech I/O to use dictation.")


class ApolloChatCore(QFrame):
    """Same painted core, docked at the top of Chat and animated on entry."""
    wake_changed = Signal(bool)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName('apolloChatCore')
        self.setStyleSheet('QFrame#apolloChatCore{background:#020605;border:1px solid #193c27;border-radius:12px;} '
                           'QFrame#apolloChatCore QLabel,QFrame#apolloChatCore QCheckBox{background:transparent;border:0;color:#a9d9b9;}')
        self.canvas = ApolloCoreCanvas(self)
        self.canvas.show_side_labels = False
        self.canvas.setMinimumHeight(0)
        self.canvas.lower()
        layout = QHBoxLayout(self); layout.setContentsMargins(14, 8, 14, 8)
        status = QVBoxLayout()
        self.title = QLabel('APOLLO'); self.title.setStyleSheet('color:#8dffb3;font-size:16px;font-weight:600')
        self.detail = QLabel('Ready when you are'); self.detail.setWordWrap(True); self.detail.setMaximumWidth(145)
        status.addWidget(self.title); status.addWidget(self.detail)
        layout.addLayout(status); layout.addStretch()
        voice = QVBoxLayout()
        self.wake = QCheckBox('Wake word: Apollo')
        self.wake.setToolTip('Enable the microphone for this session. Say Apollo, pause, then speak. Review the captured message before sending.')
        self.wake.toggled.connect(self.wake_changed)
        self.wake_status = QLabel('Off · microphone closed')
        self.wake_status.setWordWrap(True); self.wake_status.setMaximumWidth(155)
        voice.addWidget(self.wake); voice.addWidget(self.wake_status)
        layout.addLayout(voice)
        self._core_height = 100
        self.setFixedHeight(100)
        self.entry_animation = QPropertyAnimation(self, b'coreHeight', self)
        self.entry_animation.setDuration(480)
        self.entry_animation.setEasingCurve(QEasingCurve.OutCubic)
        self.entry_animation.valueChanged.connect(lambda _: self.canvas.update())

    def _get_height(self): return self._core_height
    def _set_height(self, value):
        self._core_height = int(value); self.setFixedHeight(int(value))
    coreHeight = Property(int, _get_height, _set_height)

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self.canvas.setGeometry(self.rect().adjusted(1, 1, -1, -1))

    def set_activity(self, activity):
        self.canvas.set_activity(activity)
        if self.title.text() != activity.title: self.title.setText(activity.title)
        if self.detail.text() != activity.detail: self.detail.setText(activity.detail)

    def enter(self, source=None, reduced_motion=False):
        self.entry_animation.stop()
        self.canvas.set_reduced_motion(reduced_motion)
        if source is not None: self.canvas.copy_motion_from(source)
        if reduced_motion:
            self._set_height(100); return
        expanded = min(240, max(140, int(self.window().height() * .25)))
        self._set_height(expanded)
        self.entry_animation.setStartValue(expanded)
        self.entry_animation.setEndValue(100)
        self.entry_animation.start()

    def hideEvent(self, event):
        self.entry_animation.stop(); self._set_height(100)
        super().hideEvent(event)

    def set_wake_status(self, enabled, text, available=True):
        self.wake.blockSignals(True); self.wake.setChecked(bool(enabled)); self.wake.blockSignals(False)
        self.wake.setEnabled(bool(available) or bool(enabled))
        if self.wake_status.text() != text: self.wake_status.setText(text)
