    // ── Tab switching ────────────────────────────────────────────────────
    function switchTab(group, name, btn) {
      document.querySelectorAll(`#stap-1 .tab-btn`).forEach(b => b.classList.remove('active'));
      document.querySelectorAll(`[id^="${group}-"]`).forEach(p => p.classList.remove('active'));
      btn.classList.add('active');
      document.getElementById(`${group}-${name}`).classList.add('active');
    }

    // ── OS Detection & Selector ──────────────────────────────────────────
    const OS_CONFIG = {
      macos:          { label: 'macOS',        icon: '🍎', ext: 'p12',    format: 'modern', hint: 'Modern PKCS#12 (AES-256) — for macOS 13 Ventura and newer' },
      'macos-legacy': { label: 'macOS (old)',   icon: '🍎', ext: 'p12',    format: 'legacy', hint: 'Legacy PKCS#12 (3DES) — for macOS 12 Monterey and older' },
      ios:            { label: 'iPhone/iPad',   icon: '📱', ext: 'p12',    format: 'legacy', hint: 'Legacy PKCS#12 (3DES) — iOS/iPadOS' },
      windows:        { label: 'Windows',       icon: '🪟', ext: 'pfx',    format: 'modern', hint: 'Modern PKCS#12 as .pfx — for Windows 10 and newer' },
      'windows-legacy':{ label: 'Windows (old)',icon: '🪟', ext: 'pfx',    format: 'legacy', hint: 'Legacy PKCS#12 as .pfx — for Windows 7/8' },
      linux:          { label: 'Linux',         icon: '🐧', ext: 'tar.gz', format: 'pem',    hint: 'PEM bundle (.tar.gz) — cert.pem + key.pem + CA chain' },
      android:        { label: 'Android',       icon: '🤖', ext: 'p12',    format: 'modern', hint: 'Modern PKCS#12 — for Android 9+' },
    };

    // OS auto-detection
    function detectOS() {
      const ua = navigator.userAgent;
      const platform = navigator.platform || '';

      if (/iPhone|iPad|iPod/.test(ua)) return 'ios';
      if (/Android/.test(ua)) return 'android';
      if (/Win/.test(platform) || /Windows/.test(ua)) {
        // Windows version detection
        const m = ua.match(/Windows NT (\d+\.\d+)/);
        if (m) {
          const ver = parseFloat(m[1]);
          return ver >= 10 ? 'windows' : 'windows-legacy';
        }
        return 'windows';
      }
      if (/Mac/.test(platform) || /Macintosh/.test(ua)) {
        // macOS version detection (e.g. "Mac OS X 10_15_7" or "Mac OS X 14_0")
        const m = ua.match(/Mac OS X (\d+)[_.](\d+)/);
        if (m) {
          const major = parseInt(m[1]);
          const minor = parseInt(m[2]);
          // macOS 10.16+ is Big Sur, 11=Big Sur, 12=Monterey, 13=Ventura
          const realMajor = major >= 11 ? major : (major === 10 && minor >= 16 ? 11 : major);
          return realMajor >= 13 ? 'macos' : 'macos-legacy';
        }
        return 'macos';
      }
      if (/Linux/.test(platform) || /Linux/.test(ua)) return 'linux';
      return 'macos';
    }

    function getOSVersion() {
      const ua = navigator.userAgent;
      if (/iPhone|iPad|iPod/.test(ua)) {
        const m = ua.match(/OS (\d+)[_.](\d+)/);
        return m ? `iOS ${m[1]}.${m[2]}` : 'iOS';
      }
      if (/Android/.test(ua)) {
        const m = ua.match(/Android (\d+[\.\d]*)/);
        return m ? `Android ${m[1]}` : 'Android';
      }
      if (/Windows NT/.test(ua)) {
        const m = ua.match(/Windows NT (\d+\.\d+)/);
        const map = {'10.0':'10/11','6.3':'8.1','6.2':'8','6.1':'7','6.0':'Vista'};
        return m ? `Windows ${map[m[1]] || m[1]}` : 'Windows';
      }
      if (/Macintosh/.test(ua)) {
        const m = ua.match(/Mac OS X (\d+)[_.](\d+)/);
        if (m) {
          const major = parseInt(m[1]);
          const minor = parseInt(m[2]);
          const realMajor = major >= 11 ? major : (major === 10 && minor >= 16 ? 11 : major);
          const names = {10:'Yosemite',11:'Big Sur',12:'Monterey',13:'Ventura',14:'Sonoma',15:'Sequoia'};
          return `macOS ${realMajor}` + (names[realMajor] ? ` ${names[realMajor]}` : '');
        }
        return 'macOS';
      }
      return '';
    }

    let _selectedOS = 'macos';

    function selectOS(osKey, btn) {
      _selectedOS = osKey;
      document.getElementById('selected-os').value = osKey;

      // Update button highlights
      document.querySelectorAll('#os-selector .os-btn').forEach(b => b.classList.remove('selected'));
      if (btn) btn.classList.add('selected');

      // Update format hint
      const cfg = OS_CONFIG[osKey] || OS_CONFIG['macos'];
      document.getElementById('os-format-hint').textContent = cfg.hint;

      // Update download button label
      const extLabel = cfg.ext === 'tar.gz' ? '.tar.gz (PEM)' : `.${cfg.ext} (PKCS#12)`;
      document.getElementById('cert-btn-label').textContent = `Download Certificate (${extLabel})`;

      // Update Root CA download link
      updateCaDownloadLink(osKey);
    }

    function updateCaDownloadLink(osKey) {
      const btn = document.getElementById('ca-download-btn');
      const label = document.getElementById('ca-download-label');
      if (!btn || !label) return;

      if (osKey === 'linux') {
        btn.href = '/onboarding/ca.crt?format=pem';
        label.textContent = 'Download Root CA (root-ca.crt)';
      } else {
        btn.href = '/onboarding/ca.crt';
        label.textContent = 'Download Root CA (root-ca.cer)';
      }
    }

    // Run on page load
    (function initOS() {
      const detected = detectOS();
      const version = getOSVersion();
      _selectedOS = detected;
      document.getElementById('selected-os').value = detected;

      // Set version labels
      const btn = document.querySelector(`[data-os="${detected}"]`);
      if (btn) {
        btn.classList.add('selected');
        const verEl = btn.querySelector('.os-ver');
        if (verEl && version) verEl.textContent = version;
      }

      // Set hint + button label
      const cfg = OS_CONFIG[detected] || OS_CONFIG['macos'];
      document.getElementById('os-format-hint').textContent = cfg.hint;
      const extLabel = cfg.ext === 'tar.gz' ? '.tar.gz (PEM)' : `.${cfg.ext} (PKCS#12)`;
      document.getElementById('cert-btn-label').textContent = `Download Certificate (${extLabel})`;

      updateCaDownloadLink(detected);
    })();

    // ── Certificate download ─────────────────────────────────────────────
    async function downloadCert(e) {
      e.preventDefault();
      const email = document.getElementById('cert-email').value.trim();
      const osType = document.getElementById('selected-os').value || 'macos';
      const btn = document.getElementById('cert-btn');
      const result = document.getElementById('cert-result');

      if (!email) return;

      btn.disabled = true;
      btn.innerHTML = '<div class="spinner"></div><span>Loading…</span>';
      result.innerHTML = '';

      try {
        const resp = await fetch('/onboarding/my-cert', {
          method: 'POST',
          headers: { 'Content-Type': 'application/x-www-form-urlencoded' },
          body: `email=${encodeURIComponent(email)}&os_type=${encodeURIComponent(osType)}`,
        });

        if (resp.status === 404) {
          result.innerHTML = `
            <div class="p-4 bg-yellow-900/30 border border-yellow-800/50 rounded-xl text-yellow-300 text-sm fade-in">
              <p class="font-medium">No certificate found</p>
              <p class="text-yellow-400 mt-1">Ask your administrator to create one for <strong>${escHtml(email)}</strong>.</p>
            </div>`;
          return;
        }

        if (!resp.ok) {
          const txt = await resp.text();
          result.innerHTML = `
            <div class="p-4 bg-red-900/30 border border-red-800/50 rounded-xl text-red-300 text-sm fade-in">
              <p class="font-medium">An error occurred</p>
              <p class="text-red-400 mt-1 font-mono text-xs">${escHtml(txt)}</p>
            </div>`;
          return;
        }

        const data = await resp.json();
        showCertResult(email, data.password, data.download_url, data.file_ext, osType);

      } catch (err) {
        result.innerHTML = `
          <div class="p-4 bg-red-900/30 border border-red-800/50 rounded-xl text-red-300 text-sm fade-in">
            <p class="font-medium">Network error</p>
            <p class="text-red-400 mt-1 text-xs">${escHtml(String(err))}</p>
          </div>`;
      } finally {
        btn.disabled = false;
        const cfg = OS_CONFIG[osType] || OS_CONFIG['macos'];
        const extLabel = cfg.ext === 'tar.gz' ? '.tar.gz (PEM)' : `.${cfg.ext} (PKCS#12)`;
        btn.innerHTML = `<svg class="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
          <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M4 16v1a3 3 0 003 3h10a3 3 0 003-3v-1m-4-4l-4 4m0 0l-4-4m4 4V4"/>
        </svg><span>Download Certificate (${extLabel})</span>`;
      }
    }

    function showCertResult(email, password, downloadUrl, fileExt, osType) {
      const safeEmail = escHtml(email);
      const safePass = escHtml(password);
      const cfg = OS_CONFIG[osType] || OS_CONFIG['macos'];
      const filename = `${email.replace('@','_').replace(/\./g,'_')}-ocpp.${fileExt || cfg.ext}`;

      // Build OS-specific install instructions
      const installInstructions = {
        macos: `
          <p><strong class="text-white">macOS:</strong> Double-click the .p12 file → enter the password → Keychain Access stores it in the Login keychain</p>`,
        'macos-legacy': `
          <p><strong class="text-white">macOS (old):</strong> Double-click the .p12 file → enter the password → Keychain Access</p>`,
        ios: `
          <p><strong class="text-white">iPhone/iPad:</strong> Send the .p12 file to your device (AirDrop or email) → tap to install → Go to Settings → Profile Downloaded → Install</p>`,
        windows: `
          <p><strong class="text-white">Windows:</strong> Double-click the .pfx file → Import Certificate → Current User → enter the password → Finish</p>`,
        'windows-legacy': `
          <p><strong class="text-white">Windows:</strong> Double-click the .pfx file → Import Certificate → enter the password → Finish</p>`,
        linux: `
          <p><strong class="text-white">Linux (Firefox):</strong> Settings → Privacy → View Certificates → Your Certificates → Import → choose the .pem file inside the .tar.gz</p>
          <p class="mt-1 text-gray-500 text-xs">First extract: <code class="bg-gray-800 px-1 rounded">tar xzf certificates.tar.gz</code> → import <code class="bg-gray-800 px-1 rounded">*-cert.pem</code> in Firefox. Password is needed for the private key.</p>`,
        android: `
          <p><strong class="text-white">Android:</strong> Open the .p12 file from Downloads → enter the password → give the certificate a name → Save</p>`,
      };

      const instructions = installInstructions[osType] || installInstructions['macos'];
      const passLabel = fileExt === 'tar.gz' ? 'Key password' : 'PKCS#12 password';

      document.getElementById('cert-result').innerHTML = `
        <div class="space-y-3 fade-in">
          <div class="p-4 bg-green-900/30 border border-green-800/50 rounded-xl space-y-3">
            <p class="text-green-300 font-medium text-sm">✅ Certificate created for ${safeEmail}</p>

            <div class="space-y-1">
              <p class="text-xs text-gray-400">${escHtml(passLabel)} <span class="text-yellow-400">(save this — shown only once)</span>:</p>
              <div class="flex items-center gap-2">
                <code id="p12-password" class="flex-1 bg-gray-950 border border-gray-700 rounded-lg px-3 py-2 font-mono text-sm text-green-300 select-all">${safePass}</code>
                <button onclick="copyPassword()" class="copy-btn flex-shrink-0 px-3 py-2 bg-gray-800 hover:bg-gray-700 rounded-lg text-gray-300 text-xs transition-colors" title="Copy password">
                  📋 Copy
                </button>
              </div>
            </div>

            <a href="${downloadUrl}" download="${filename}"
               class="inline-flex items-center gap-2 px-4 py-2.5 rounded-xl font-semibold text-sm
                      bg-brand hover:bg-sky-400 text-white transition-all active:scale-95">
              <svg class="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M4 16v1a3 3 0 003 3h10a3 3 0 003-3v-1m-4-4l-4 4m0 0l-4-4m4 4V4"/>
              </svg>
              Download ${escHtml(filename)}
            </a>
          </div>

          <div class="p-3 bg-gray-800/40 border border-gray-700/50 rounded-xl text-xs text-gray-400 space-y-1">
            <p class="font-medium text-gray-300">📋 Installation instructions</p>
            ${instructions}
            <p class="text-yellow-500 mt-2">⚠️ Keep the password safe — you will need it during installation and the link will expire.</p>
          </div>
        </div>`;
    }

    function copyPassword() {
      const el = document.getElementById('p12-password');
      if (el) {
        navigator.clipboard.writeText(el.textContent).then(() => {
          const btn = document.querySelector('.copy-btn');
          if (btn) { btn.textContent = '✅ Copied'; setTimeout(() => btn.innerHTML = '📋 Copy', 2000); }
        });
      }
    }

    function escHtml(s) {
      return String(s).replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;').replace(/"/g,'&quot;');
    }

    // ── DNS Check ────────────────────────────────────────────────────────
    async function checkDns() {
      const el = document.getElementById('dns-result');
      try {
        // Check connectivity to this admin panel
        const controller = new AbortController();
        const timeout = setTimeout(() => controller.abort(), 5000);
        await fetch('/health', {
          method: 'HEAD',
          mode: 'same-origin',
          signal: controller.signal,
        });
        clearTimeout(timeout);
        el.innerHTML = `
          <span class="text-2xl">✅</span>
          <div>
            <p class="text-green-300 font-medium text-sm">Connected!</p>
            <p class="text-gray-400 text-xs mt-0.5">The admin panel is reachable from your device.</p>
          </div>`;
      } catch (err) {
        const isAborted = err.name === 'AbortError';
        el.innerHTML = `
          <span class="text-2xl">${isAborted ? '⏱️' : '⚠️'}</span>
          <div class="space-y-1">
            <p class="text-yellow-300 font-medium text-sm">${isAborted ? 'Time-out' : 'Check manually'}</p>
            <p class="text-gray-400 text-xs">
              ${isAborted ? 'No response within 5 seconds.' : 'Could not verify connectivity automatically.'}
              If you can read this page, your connection is working.
            </p>
          </div>`;
      }
    }

    // Run DNS check on load
    if (typeof fetch !== 'undefined') {
      checkDns();
    } else {
      document.getElementById('dns-result').innerHTML = `
        <span class="text-yellow-400">⚠️</span>
        <span class="text-gray-400 text-sm">DNS check not supported in this browser.</span>`;
    }
