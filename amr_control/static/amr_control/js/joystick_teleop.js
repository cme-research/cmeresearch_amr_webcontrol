// Touch-joystick teleop for the AMR Control Dashboard.
//
// Two nipplejs sticks publish a continuous TwistStamped stream to the Django
// /amr_control/joystick_cmd/ endpoint at 20 Hz while a finger is on a stick.
//
// Safety, layered:
//   1) Server clamps every axis (views.py MAX_LINEAR_X/Y/ANGULAR_Z).
//   2) twist_mux on the robot side brakes after 500 ms of silence.
//   3) MQTT Last-Will publishes a zero TwistStamped if Django dies.
//   4) Page visibilitychange / pagehide / blur / offline -> immediate zero + disarm.
//   5) pointercancel via nipplejs 'end' -> explicit zero (TurtleBot PR #75 lesson).
//   6) Auto-disarm after ARM_TIMEOUT_MS without user input.
//   7) "Aktivieren" gate must be tapped before sticks accept input.
//   8) AbortController-based request supersession keeps queue depth at 1.
//   9) Browser-side caps mirror server caps; deadzone kills tremor/drift.

(function () {
    'use strict';

    // Resolved at init() from the joystick-arm-bar data-endpoint attribute,
    // which the Django template renders via {% url 'joystick_cmd' %}.
    let ENDPOINT         = '/joystick_cmd/';
    const TICK_MS        = 50;             // 20 Hz publish loop
    const ARM_TIMEOUT_MS = 60 * 1000;      // disarm after 60 s of zero input
    const DEADZONE       = 0.08;           // 8 % of stick radius
    const MAX_LINEAR_X   = 0.4;            // m/s   -- mirror views.py
    const MAX_LINEAR_Y   = 0.3;            // m/s
    const MAX_ANGULAR_Z  = 0.8;            // rad/s
    const ERROR_BUDGET   = 3;              // consecutive network errors -> disarm

    let armed           = false;
    let engagedLinear   = false;
    let engagedAngular  = false;
    let linVec          = { x: 0, y: 0 };  // nipplejs vector, -1..1
    let angVal          = 0;               // nipplejs vector.x of angular stick
    let lastInputAt     = 0;
    let lastTickAt      = 0;
    let rafId           = null;
    let inflightAbort   = null;
    let errorStreak     = 0;

    let linJoy   = null;
    let angJoy   = null;
    let statusEl = null;
    let armBtn   = null;
    let stopBtn  = null;
    let cmdEl    = null;
    let txEl     = null;
    let linZone  = null;
    let angZone  = null;

    function getCsrfToken() {
        const m = document.cookie.match(/(?:^|;\s*)csrftoken=([^;]+)/);
        return m ? decodeURIComponent(m[1]) : '';
    }

    function applyDeadzone(v) {
        return Math.abs(v) < DEADZONE ? 0 : v;
    }

    function clamp(v, lim) {
        if (v > lim) return lim;
        if (v < -lim) return -lim;
        return v;
    }

    // Mecanum mapping, ROS REP-103 conventions:
    //   Linear stick: y-up   = +linear_x (forward)
    //                 x-right = -linear_y (strafe; left is +y in REP-103)
    //   Angular stick: x-right = -angular_z (clockwise = negative yaw)
    function buildTwist() {
        const lx = clamp(applyDeadzone(linVec.y) * MAX_LINEAR_X,  MAX_LINEAR_X);
        const ly = clamp(-applyDeadzone(linVec.x) * MAX_LINEAR_Y, MAX_LINEAR_Y);
        const az = clamp(-applyDeadzone(angVal)   * MAX_ANGULAR_Z, MAX_ANGULAR_Z);
        return { linear_x: lx, linear_y: ly, angular_z: az };
    }

    function setStatus(text, cls) {
        if (!statusEl) return;
        statusEl.textContent = text;
        statusEl.className = 'arm-status' + (cls ? ' ' + cls : '');
    }

    function setArmedUI() {
        if (armed) {
            linZone.classList.remove('disarmed');
            angZone.classList.remove('disarmed');
            armBtn.classList.add('armed');
            armBtn.textContent = 'Sperren';
        } else {
            linZone.classList.add('disarmed');
            angZone.classList.add('disarmed');
            armBtn.classList.remove('armed');
            armBtn.textContent = 'Aktivieren';
        }
    }

    function postTwist(twist) {
        // Queue depth 1: cancel any in-flight POST so we never apply stale velocity.
        if (inflightAbort) {
            try { inflightAbort.abort(); } catch (_) { /* noop */ }
        }
        inflightAbort = new AbortController();
        fetch(ENDPOINT, {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
                'X-Requested-With': 'XMLHttpRequest',
                'X-CSRFToken': getCsrfToken(),
            },
            body: JSON.stringify(twist),
            signal: inflightAbort.signal,
        }).then(function (r) {
            inflightAbort = null;
            if (!r.ok) {
                errorStreak += 1;
                if (errorStreak >= ERROR_BUDGET) disarm({ reason: 'connection' });
                return;
            }
            errorStreak = 0;
            if (txEl) txEl.textContent = 'Letztes Kommando: gerade eben';
        }).catch(function (err) {
            inflightAbort = null;
            if (err && err.name === 'AbortError') return;
            errorStreak += 1;
            if (errorStreak >= ERROR_BUDGET) disarm({ reason: 'connection' });
        });
    }

    // Fire-and-forget zero. Uses keepalive so it survives pagehide on supported
    // browsers. Does NOT abort the in-flight loop — this is an additional safety
    // event, not a supersession.
    function publishZeroOnce(reason) {
        try {
            fetch(ENDPOINT, {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                    'X-Requested-With': 'XMLHttpRequest',
                    'X-CSRFToken': getCsrfToken(),
                },
                body: JSON.stringify({ linear_x: 0, linear_y: 0, angular_z: 0 }),
                keepalive: true,
            }).catch(function () { /* silent — best-effort */ });
        } catch (_) { /* noop */ }
        if (txEl) txEl.textContent = 'STOP gesendet (' + (reason || 'unspecified') + ')';
    }

    function scheduleLoop() {
        if (rafId !== null) return;
        lastTickAt = 0;
        const tick = function (now) {
            if (!armed) { rafId = null; return; }
            if ((now - lastInputAt) > ARM_TIMEOUT_MS) {
                disarm({ reason: 'idle' });
                return;
            }
            if (now - lastTickAt >= TICK_MS) {
                lastTickAt = now;
                const t = buildTwist();
                if (cmdEl) {
                    cmdEl.textContent =
                        'v=' + t.linear_x.toFixed(2) +
                        ' m/s · vy=' + t.linear_y.toFixed(2) +
                        ' m/s · ω=' + t.angular_z.toFixed(2) +
                        ' rad/s';
                }
                // Only emit while at least one stick is touched. When both
                // released we already published one explicit zero (PR #75
                // lesson); twist_mux's 0.5 s watchdog then brakes the robot.
                if (engagedLinear || engagedAngular) postTwist(t);
            }
            rafId = requestAnimationFrame(tick);
        };
        rafId = requestAnimationFrame(tick);
    }

    function cancelLoop() {
        if (rafId !== null) {
            cancelAnimationFrame(rafId);
            rafId = null;
        }
    }

    function arm() {
        if (armed) return;
        armed = true;
        lastInputAt = performance.now();
        setArmedUI();
        setStatus('Aktiv', 'armed');
        scheduleLoop();
    }

    function disarm(opts) {
        const wasArmed = armed;
        armed = false;
        engagedLinear = false;
        engagedAngular = false;
        linVec = { x: 0, y: 0 };
        angVal = 0;
        cancelLoop();
        const reason = opts && opts.reason ? opts.reason : 'user';
        if (wasArmed) publishZeroOnce(reason);
        setArmedUI();
        const labels = {
            idle:       ['Auto-gesperrt (Idle)',         'warning'],
            visibility: ['Auto-gesperrt (Tab versteckt)', 'warning'],
            offline:    ['Auto-gesperrt (Offline)',      'error'],
            connection: ['Verbindung verloren',          'error'],
            stop:       ['STOP gedrückt',                'warning'],
            user:       ['Gesperrt',                     ''],
        };
        const [text, cls] = labels[reason] || ['Gesperrt', ''];
        setStatus(text, cls);
    }

    function initJoysticks() {
        linZone = document.getElementById('joy-linear');
        angZone = document.getElementById('joy-angular');
        if (!linZone || !angZone) return false;

        const accent = (getComputedStyle(document.documentElement)
            .getPropertyValue('--accent-primary') || '#2c5282').trim();

        linJoy = nipplejs.create({
            zone: linZone,
            mode: 'static',
            position: { left: '50%', top: '50%' },
            color: accent,
            size: 130,
            restJoystick: true,
        });
        angJoy = nipplejs.create({
            zone: angZone,
            mode: 'static',
            position: { left: '50%', top: '50%' },
            color: accent,
            size: 130,
            restJoystick: true,
            lockX: true,   // angular stick: left/right only (lockX = lock TO X-axis)
        });

        linJoy.on('start', function () {
            if (!armed) return;
            engagedLinear = true;
            lastInputAt = performance.now();
        });
        linJoy.on('move', function (_evt, data) {
            if (!armed) return;
            const v = data && data.vector ? data.vector : { x: 0, y: 0 };
            linVec = { x: v.x, y: v.y };
            lastInputAt = performance.now();
        });
        // 'end' fires for both pointerup AND pointercancel — nipplejs handles
        // the iOS gesture / system swipe case for us.
        linJoy.on('end', function () {
            engagedLinear = false;
            linVec = { x: 0, y: 0 };
            if (armed) publishZeroOnce('linear_release');
        });

        angJoy.on('start', function () {
            if (!armed) return;
            engagedAngular = true;
            lastInputAt = performance.now();
        });
        angJoy.on('move', function (_evt, data) {
            if (!armed) return;
            const v = data && data.vector ? data.vector : { x: 0, y: 0 };
            angVal = v.x;
            lastInputAt = performance.now();
        });
        angJoy.on('end', function () {
            engagedAngular = false;
            angVal = 0;
            if (armed) publishZeroOnce('angular_release');
        });

        return true;
    }

    function attachLifecycleHandlers() {
        document.addEventListener('visibilitychange', function () {
            if (document.hidden && armed) disarm({ reason: 'visibility' });
        });
        window.addEventListener('pagehide', function () {
            if (armed) disarm({ reason: 'visibility' });
        });
        // beforeunload: best-effort zero before page tears down.
        window.addEventListener('beforeunload', function () {
            publishZeroOnce('unload');
        });
        window.addEventListener('offline', function () {
            if (armed) disarm({ reason: 'offline' });
        });
        window.addEventListener('online', function () {
            if (!armed) setStatus('Gesperrt');
        });
    }

    function attachButtonHandlers() {
        armBtn.addEventListener('click', function () {
            if (armed) disarm({ reason: 'user' });
            else arm();
        });
        // pointerdown (not click) on STOP: react on press, not release.
        // For a panic stop, milliseconds matter.
        stopBtn.addEventListener('pointerdown', function (ev) {
            ev.preventDefault();
            disarm({ reason: 'stop' });
        });
        // Fallback for non-pointer-event browsers and keyboard activation.
        stopBtn.addEventListener('click', function () {
            disarm({ reason: 'stop' });
        });
    }

    function init() {
        if (typeof nipplejs === 'undefined') {
            console.warn('[joystick_teleop] nipplejs not loaded — UI disabled');
            return;
        }
        statusEl = document.getElementById('joy-arm-status');
        armBtn   = document.getElementById('joy-arm-btn');
        stopBtn  = document.getElementById('joy-stop');
        cmdEl    = document.getElementById('joy-cmd-readout');
        txEl     = document.getElementById('joy-tx-readout');
        if (!statusEl || !armBtn || !stopBtn) {
            console.warn('[joystick_teleop] required DOM nodes missing');
            return;
        }
        const armBar = armBtn.closest('.joystick-arm-bar');
        const ep = armBar && armBar.getAttribute('data-endpoint');
        if (ep) ENDPOINT = ep;
        if (!initJoysticks()) {
            setStatus('Joystick-Init fehlgeschlagen', 'error');
            return;
        }
        attachLifecycleHandlers();
        attachButtonHandlers();
        setArmedUI();
        setStatus('Gesperrt');
    }

    if (document.readyState === 'loading') {
        document.addEventListener('DOMContentLoaded', init);
    } else {
        init();
    }
})();
