/**
 * TQC Inspection Tool — Shared JavaScript
 */

/* ── Keyboard shortcuts: ESC back, ← → prev/next ──────────────────── */
document.addEventListener('keydown', function(e) {
  // Ignore when typing in inputs
  if (e.target.tagName === 'INPUT' || e.target.tagName === 'TEXTAREA' || e.target.isContentEditable) return;

  if (e.key === 'Escape') {
    if (document.querySelector('.lightbox')) return;
    e.preventDefault();
    var params = new URLSearchParams(location.search);
    var workshop = params.get('workshop') || 'ODL';
    var quarter = params.get('quarter') || '2026 Q2';
    var country = params.get('country') || 'Uruguay';
    var ref = params.get('ref') || '';
    var base = (ref === 'review') ? '/review' : '/';
    var qs = '?country=' + encodeURIComponent(country) + '&workshop=' + encodeURIComponent(workshop) + '&quarter=' + encodeURIComponent(quarter) + '&lang=' + encodeURIComponent(params.get('lang')||'en');
    if (location.pathname.startsWith('/item/')) {
      location.href = base + qs;
    } else if (location.pathname === '/review' || location.pathname === '/export') {
      location.href = '/' + qs;
    }
  }

  if (e.key === 'ArrowLeft') {
    var prev = document.querySelector('.js-prev');
    if (prev) { e.preventDefault(); prev.click(); }
  }
  if (e.key === 'ArrowRight') {
    var next = document.querySelector('.js-next');
    if (next) { e.preventDefault(); next.click(); }
  }
});

/* ── Toast Notifications ───────────────────────────────────────────── */
function showToast(msg, type, undoAction) {
  type = type || 'info';
  var container = document.getElementById('toast-container');
  var el = document.createElement('div');
  el.className = 'toast ' + type;
  el.textContent = msg;

  if (undoAction) {
    var undoBtn = document.createElement('button');
    undoBtn.textContent = 'Undo';
    undoBtn.style.cssText = 'margin-left:auto;background:none;border:1px solid currentColor;color:inherit;padding:4px 10px;border-radius:6px;font-weight:600;font-size:0.78rem;cursor:pointer;font-family:inherit;flex-shrink:0;';
    undoBtn.addEventListener('click', function(e) {
      e.stopPropagation();
      clearTimeout(timer);
      el.classList.add('removing');
      setTimeout(function() { el.remove(); }, 300);
      undoAction();
    });
    el.appendChild(undoBtn);
  }

  container.appendChild(el);
  var timer = setTimeout(function() {
    el.classList.add('removing');
    setTimeout(function() { el.remove(); }, 300);
  }, 4000);
  el.addEventListener('click', function() {
    clearTimeout(timer);
    el.classList.add('removing');
    setTimeout(function() { el.remove(); }, 300);
  });
}

/* ── Pull-to-Refresh ───────────────────────────────────────────────── */
(function() {
  var pct = 0, pulling = false, startY = 0, el = null;
  document.addEventListener('touchstart', function(e) {
    if (window.scrollY > 5) return;
    startY = e.touches[0].clientY;
    pulling = true;
  }, {passive: true});
  document.addEventListener('touchmove', function(e) {
    if (!pulling) return;
    var dy = e.touches[0].clientY - startY;
    if (dy > 30 && window.scrollY < 5) {
      if (!el) {
        el = document.createElement('div');
        el.style.cssText = 'position:fixed;top:0;left:0;right:0;height:4px;background:var(--blue);z-index:999;transform:scaleX(0);transform-origin:left;transition:none;';
        document.body.appendChild(el);
      }
      pct = Math.min(dy / 120, 1);
      el.style.transform = 'scaleX(' + pct + ')';
    }
  }, {passive: true});
  document.addEventListener('touchend', function() {
    if (!pulling) return;
    pulling = false;
    if (pct >= 1) {
      el.style.transition = 'transform 0.15s ease';
      el.style.transform = 'scaleX(1)';
      setTimeout(function() {
        if (typeof syncRules === 'function') syncRules();
        setTimeout(function() { el.style.transform = 'scaleX(0)'; }, 300);
      }, 150);
    } else if (el) {
      el.style.transition = 'transform 0.2s ease';
      el.style.transform = 'scaleX(0)';
    }
    pct = 0;
  }, {passive: true});
})();

/* ── Action Sheet ──────────────────────────────────────────────────── */
function showSheet(title, buttons) {
  var overlay = document.createElement('div');
  overlay.className = 'sheet-overlay';
  var sheet = document.createElement('div');
  sheet.className = 'sheet';
  if (title) {
    var t = document.createElement('div');
    t.className = 'sheet-title';
    t.textContent = title;
    sheet.appendChild(t);
  }
  buttons.forEach(function(b) {
    var btn = document.createElement('button');
    btn.className = 'sheet-btn';
    if (b.destructive) btn.className += ' destructive';
    if (b.cancel) btn.className += ' sheet-cancel';
    btn.textContent = b.label;
    btn.addEventListener('click', function() {
      closeSheet(overlay, sheet, b.action);
    });
    sheet.appendChild(btn);
  });
  overlay.appendChild(sheet);
  overlay.addEventListener('click', function(e) {
    if (e.target === overlay) closeSheet(overlay, sheet);
  });
  document.body.appendChild(overlay);
}
function closeSheet(overlay, sheet, action) {
  overlay.classList.add('closing');
  sheet.classList.add('closing');
  setTimeout(function() {
    overlay.remove();
    if (typeof action === 'function') action();
  }, 250);
}

/* ── Button Loading ────────────────────────────────────────────────── */
function setLoading(btn, loading) {
  if (loading) {
    btn.classList.add('loading');
    btn.disabled = true;
    btn._origText = btn.textContent;
    btn.textContent = btn._origText.replace(/^.*$/, '').trim() || 'Working';
  } else {
    btn.classList.remove('loading');
    btn.disabled = false;
    if (btn._origText) btn.textContent = btn._origText;
  }
}

/* ── confirmScore ──────────────────────────────────────────────────── */
function confirmScore(sn, workshop, btnEl) {
  var scoreInput = document.getElementById('score-input');
  var remarksInput = document.getElementById('remarks-input');
  var autoScoreEl = document.getElementById('auto-score-val');
  var score = scoreInput ? parseFloat(scoreInput.value) : null;
  var remarks = remarksInput ? remarksInput.value.trim() : '';
  var autoScore = autoScoreEl ? parseFloat(autoScoreEl.textContent) || null : null;

  if (score === null || isNaN(score)) {
    showToast('Please enter a valid score', 'error');
    return;
  }

  var body = { sn: sn, workshop: workshop, score: score, remarks: remarks };
  if (autoScore !== null) body.auto_score = autoScore;

  if (btnEl) setLoading(btnEl, true);

  fetch('/api/confirm', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body)
  })
    .then(function(r) { return r.json(); })
    .then(function(data) {
      if (btnEl) setLoading(btnEl, false);
      if (data.ok) {
        showToast('Score confirmed', 'success', function() {
          fetch('/api/undo-confirm', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ sn: sn, workshop: workshop })
          }).then(function() { location.reload(); });
        });
        if (btnEl) {
          btnEl.textContent = 'Confirmed';
          btnEl.classList.remove('btn-primary');
          btnEl.classList.add('btn-success');
          btnEl.disabled = true;
        }
        setTimeout(function() { location.reload(); }, 4000);
      } else {
        showToast('Failed: ' + (data.error || 'Unknown error'), 'error');
      }
    })
    .catch(function(err) {
      if (btnEl) setLoading(btnEl, false);
      showToast('Network error: ' + err.message, 'error');
    });
}

/* ── unconfirmScore ───────────────────────────────────────────────── */
function unconfirmScore(sn, workshop) {
  showSheet('Cancel this confirmation?', [
    { label: 'Cancel Confirmation', destructive: true, action: function() {
      fetch('/api/undo-confirm', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ sn: sn, workshop: workshop })
      })
        .then(function(r) { return r.json(); })
        .then(function(data) {
          if (data.ok) {
            showToast('Confirmation cancelled', 'success');
            setTimeout(function() { location.reload(); }, 600);
          } else {
            showToast('Failed: ' + (data.error || 'Unknown error'), 'error');
          }
        })
        .catch(function(err) { showToast('Network error: ' + err.message, 'error'); });
    }},
    { label: 'Keep', cancel: true, action: function() {} }
  ]);
}

/* ── confirmAll ────────────────────────────────────────────────────── */
function confirmAll(workshop) {
  showSheet('Confirm all auto-scored items?', [
    { label: 'Confirm All', destructive: false, action: function() {
      fetch('/api/confirm-batch', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ workshop: workshop })
      })
        .then(function(r) { return r.json(); })
        .then(function(data) {
          if (data.ok) {
            showToast('Confirmed ' + data.updated + ' items', 'success');
            setTimeout(function() { location.reload(); }, 800);
          } else {
            showToast('Failed: ' + (data.error || 'Unknown error'), 'error');
          }
        })
        .catch(function(err) {
          showToast('Network error: ' + err.message, 'error');
        });
    }},
    { label: 'Cancel', cancel: true, action: function() {} }
  ]);
}

/* ── uploadEvidence ────────────────────────────────────────────────── */
function uploadEvidence(sn, workshop) {
  var input = document.createElement('input');
  input.type = 'file';
  input.accept = 'image/*,video/*';
  input.onchange = function() {
    var file = input.files[0];
    if (!file) return;
    var quarter = new URLSearchParams(location.search).get('quarter') || '2026 Q2';
    var formData = new FormData();
    formData.append('file', file);
    formData.append('sn', sn);
    formData.append('workshop', workshop);
    formData.append('quarter', quarter);
    showToast('Uploading...', 'info');
    fetch('/api/upload', { method: 'POST', body: formData })
      .then(function(r) { return r.json(); })
      .then(function(data) {
        if (data.ok) {
          showToast('Uploaded', 'success');
          setTimeout(function() { location.reload(); }, 600);
        } else {
          showToast('Upload failed: ' + (data.error || 'Unknown error'), 'error');
        }
      })
      .catch(function(err) {
        showToast('Network error: ' + err.message, 'error');
      });
  };
  input.click();
}

/* ── deleteEvidence ────────────────────────────────────────────────── */
function deleteEvidence(eid) {
  showSheet('Delete this evidence?', [
    { label: 'Delete', destructive: true, action: function() {
      fetch('/api/evidence/' + eid + '/delete', { method: 'POST' })
        .then(function(r) { return r.json(); })
        .then(function(data) {
          if (data.ok) {
            showToast('Deleted', 'success');
            setTimeout(function() { location.reload(); }, 500);
          } else {
            showToast('Delete failed: ' + (data.error || 'Unknown error'), 'error');
          }
        })
        .catch(function(err) {
          showToast('Network error: ' + err.message, 'error');
        });
    }},
    { label: 'Cancel', cancel: true, action: function() {} }
  ]);
}

/* ── runAutoScore ──────────────────────────────────────────────────── */
function runAutoScore(workshop) {
  var btn = event.target;
  setLoading(btn, true);
  fetch('/api/auto-score', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ workshop: workshop })
  })
    .then(function(r) { return r.json(); })
    .then(function(data) {
      setLoading(btn, false);
      if (data.ok) {
        showToast('Auto scored ' + data.scored + ' items', 'success');
        setTimeout(function() { location.reload(); }, 800);
      } else {
        showToast('Failed: ' + (data.error || 'Unknown error'), 'error');
      }
    })
    .catch(function(err) {
      setLoading(btn, false);
      showToast('Network error: ' + err.message, 'error');
    });
}

/* ── writeToSheet ──────────────────────────────────────────────────── */
function writeToSheet(workshop) {
  showSheet('Write confirmed scores to Google Sheet?', [
    { label: 'Write to Sheet', action: function() {
      fetch('/api/write-scores', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ workshop: workshop })
      })
        .then(function(r) { return r.json(); })
        .then(function(data) {
          if (data.ok) {
            showToast('Written to Google Sheet', 'success');
          } else {
            showToast('Write failed: ' + (data.error || 'Unknown error'), 'error');
          }
        })
        .catch(function(err) {
          showToast('Network error: ' + err.message, 'error');
        });
    }},
    { label: 'Cancel', cancel: true, action: function() {} }
  ]);
}

/* ── Image Lightbox ───────────────────────────────────────────────── */
var _lightboxEscHandler = null;
function openLightbox(url) {
  var overlay = document.createElement('div');
  overlay.className = 'lightbox';
  var img = document.createElement('img');
  img.src = url;
  img.addEventListener('click', function(e) { e.stopPropagation(); });
  overlay.appendChild(img);
  overlay.addEventListener('click', function() { closeLightbox(overlay); });
  // ESC to close
  _lightboxEscHandler = function(e) {
    if (e.key === 'Escape') { e.stopPropagation(); e.preventDefault(); closeLightbox(overlay); }
  };
  document.addEventListener('keydown', _lightboxEscHandler, true);
  document.body.appendChild(overlay);
}
function closeLightbox(overlay) {
  if (_lightboxEscHandler) { document.removeEventListener('keydown', _lightboxEscHandler, true); _lightboxEscHandler = null; }
  overlay.classList.add('closing');
  setTimeout(function() { overlay.remove(); }, 200);
}

/* ── syncRules ─────────────────────────────────────────────────────── */
function syncRules() {
  var btn = event.target;
  setLoading(btn, true);
  var quarter = new URLSearchParams(location.search).get('quarter') || '2026 Q2';
  fetch('/api/sync-rules', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ quarter: quarter })
  })
    .then(function(r) { return r.json(); })
    .then(function(data) {
      setLoading(btn, false);
      if (data.ok) {
        showToast('Rules synced', 'success');
        setTimeout(function() { location.reload(); }, 800);
      } else {
        showToast('Sync failed: ' + (data.error || 'Unknown error'), 'error');
      }
    })
    .catch(function(err) {
      setLoading(btn, false);
      showToast('Network error: ' + err.message, 'error');
    });
}
