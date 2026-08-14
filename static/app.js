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
    undoBtn.textContent = (window.TQC_I18N && TQC_I18N.undo) || 'Undo';
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
    btn.textContent = (window.TQC_I18N && TQC_I18N.working) || 'Working...';
  } else {
    btn.classList.remove('loading');
    btn.disabled = false;
    if (btn._origText) btn.textContent = btn._origText;
  }
}

/* ── Current quarter helper ────────────────────────────────────────── */
function currentQuarter() {
  return new URLSearchParams(location.search).get('quarter') || '2026 Q2';
}

/* ── API URL helper — always propagate the active country/lang ─────── */
function apiUrl(path) {
  var u = new URL(path, location.origin);
  var params = new URLSearchParams(location.search);
  var country = params.get('country');
  if (country) u.searchParams.set('country', country);
  var lang = params.get('lang');
  if (lang) u.searchParams.set('lang', lang);
  return u.toString();
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
    showToast((window.TQC_I18N && TQC_I18N.please_enter_score) || 'Please enter a valid score', 'error');
    return;
  }

  var body = { sn: sn, workshop: workshop, score: score, remarks: remarks, quarter: currentQuarter() };
  if (autoScore !== null) body.auto_score = autoScore;

  if (btnEl) setLoading(btnEl, true);

  fetch(apiUrl('/api/confirm'), {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body)
  })
    .then(function(r) { return r.json(); })
    .then(function(data) {
      if (btnEl) setLoading(btnEl, false);
      if (data.ok) {
        showToast((window.TQC_I18N && TQC_I18N.score_confirmed) || 'Score confirmed', 'success', function() {
          fetch(apiUrl('/api/undo-confirm'), {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ sn: sn, workshop: workshop, quarter: currentQuarter() })
          }).then(function() { location.reload(); });
        });
        if (btnEl) {
          btnEl.textContent = (window.TQC_I18N && TQC_I18N.confirmed) || 'Confirmed';
          btnEl.classList.remove('btn-primary');
          btnEl.classList.add('btn-success');
          btnEl.disabled = true;
        }
        setTimeout(function() { location.reload(); }, 4000);
      } else {
        showToast(((window.TQC_I18N && TQC_I18N.operation_failed) || 'Failed: {}').replace('{}', data.error || 'Unknown error'), 'error');
      }
    })
    .catch(function(err) {
      if (btnEl) setLoading(btnEl, false);
      showToast(((window.TQC_I18N && TQC_I18N.network_error) || 'Network error: {}').replace('{}', err.message), 'error');
    });
}

/* ── unconfirmScore ───────────────────────────────────────────────── */
function unconfirmScore(sn, workshop) {
  showSheet((window.TQC_I18N && TQC_I18N.cancel_confirmation) || 'Cancel this confirmation?', [
    { label: (window.TQC_I18N && TQC_I18N.cancel_confirmation_btn) || 'Cancel Confirmation', destructive: true, action: function() {
      fetch(apiUrl('/api/undo-confirm'), {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ sn: sn, workshop: workshop, quarter: currentQuarter() })
      })
        .then(function(r) { return r.json(); })
        .then(function(data) {
          if (data.ok) {
            showToast((window.TQC_I18N && TQC_I18N.confirmation_cancelled) || 'Confirmation cancelled', 'success');
            setTimeout(function() { location.reload(); }, 600);
          } else {
            showToast(((window.TQC_I18N && TQC_I18N.operation_failed) || 'Failed: {}').replace('{}', data.error || 'Unknown error'), 'error');
          }
        })
        .catch(function(err) { showToast(((window.TQC_I18N && TQC_I18N.network_error) || 'Network error: {}').replace('{}', err.message), 'error'); });
    }},
    { label: (window.TQC_I18N && TQC_I18N.keep) || 'Keep', cancel: true, action: function() {} }
  ]);
}

/* ── confirmAll ────────────────────────────────────────────────────── */
function confirmAll(workshop) {
  showSheet((window.TQC_I18N && TQC_I18N.confirm_all_title) || 'Confirm all auto-scored items?', [
    { label: (window.TQC_I18N && TQC_I18N.confirm_all) || 'Confirm All', destructive: false, action: function() {
      fetch(apiUrl('/api/confirm-batch'), {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ workshop: workshop, quarter: currentQuarter() })
      })
        .then(function(r) { return r.json(); })
        .then(function(data) {
          if (data.ok) {
            showToast(((window.TQC_I18N && TQC_I18N.batch_confirmed) || 'Confirmed {} items').replace('{}', data.updated), 'success');
            setTimeout(function() { location.reload(); }, 800);
          } else {
            showToast(((window.TQC_I18N && TQC_I18N.operation_failed) || 'Failed: {}').replace('{}', data.error || 'Unknown error'), 'error');
          }
        })
        .catch(function(err) {
          showToast(((window.TQC_I18N && TQC_I18N.network_error) || 'Network error: {}').replace('{}', err.message), 'error');
        });
    }},
    { label: (window.TQC_I18N && TQC_I18N.cancel) || 'Cancel', cancel: true, action: function() {} }
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
    var quarter = currentQuarter();
    var formData = new FormData();
    formData.append('file', file);
    formData.append('sn', sn);
    formData.append('workshop', workshop);
    formData.append('quarter', quarter);
    showToast((window.TQC_I18N && TQC_I18N.uploading) || 'Uploading...', 'info');
    fetch(apiUrl('/api/upload'), { method: 'POST', body: formData })
      .then(function(r) { return r.json(); })
      .then(function(data) {
        if (data.ok) {
          showToast((window.TQC_I18N && TQC_I18N.uploaded) || 'Uploaded', 'success');
          setTimeout(function() { location.reload(); }, 600);
        } else {
          showToast(((window.TQC_I18N && TQC_I18N.upload_failed) || 'Upload failed: {}').replace('{}', data.error || 'Unknown error'), 'error');
        }
      })
      .catch(function(err) {
        showToast(((window.TQC_I18N && TQC_I18N.network_error) || 'Network error: {}').replace('{}', err.message), 'error');
      });
  };
  input.click();
}

/* ── deleteEvidence ────────────────────────────────────────────────── */
function deleteEvidence(eid) {
  showSheet((window.TQC_I18N && TQC_I18N.delete_confirm_title) || 'Delete this evidence?', [
    { label: (window.TQC_I18N && TQC_I18N.delete_btn) || 'Delete', destructive: true, action: function() {
      fetch(apiUrl('/api/evidence/' + eid + '/delete'), { method: 'POST' })
        .then(function(r) { return r.json(); })
        .then(function(data) {
          if (data.ok) {
            showToast((window.TQC_I18N && TQC_I18N.deleted) || 'Deleted', 'success');
            setTimeout(function() { location.reload(); }, 500);
          } else {
            showToast(((window.TQC_I18N && TQC_I18N.delete_failed) || 'Delete failed: {}').replace('{}', data.error || 'Unknown error'), 'error');
          }
        })
        .catch(function(err) {
          showToast(((window.TQC_I18N && TQC_I18N.network_error) || 'Network error: {}').replace('{}', err.message), 'error');
        });
    }},
    { label: (window.TQC_I18N && TQC_I18N.cancel) || 'Cancel', cancel: true, action: function() {} }
  ]);
}

/* ── runAutoScore ──────────────────────────────────────────────────── */
function runAutoScore(workshop) {
  var btn = (typeof event !== 'undefined') ? event.target : null;
  if (btn) setLoading(btn, true);
  fetch(apiUrl('/api/auto-score'), {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ workshop: workshop, quarter: currentQuarter() })
  })
    .then(function(r) { return r.json(); })
    .then(function(data) {
      if (btn) setLoading(btn, false);
      if (data.ok) {
        showToast(((window.TQC_I18N && TQC_I18N.auto_scored) || 'Auto scored {} items').replace('{}', data.scored), 'success');
        setTimeout(function() { location.reload(); }, 800);
      } else {
        showToast(((window.TQC_I18N && TQC_I18N.operation_failed) || 'Failed: {}').replace('{}', data.error || 'Unknown error'), 'error');
      }
    })
    .catch(function(err) {
      if (btn) setLoading(btn, false);
      showToast(((window.TQC_I18N && TQC_I18N.network_error) || 'Network error: {}').replace('{}', err.message), 'error');
    });
}

/* ── writeToSheet ──────────────────────────────────────────────────── */
function writeToSheet(workshop) {
  showSheet((window.TQC_I18N && TQC_I18N.write_confirm_title) || 'Write confirmed scores to Google Sheet?', [
    { label: (window.TQC_I18N && TQC_I18N.write_to_sheet) || 'Write to Sheet', action: function() {
      fetch(apiUrl('/api/write-scores'), {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ workshop: workshop, quarter: currentQuarter() })
      })
        .then(function(r) { return r.json(); })
        .then(function(data) {
          if (data.ok) {
            showToast((window.TQC_I18N && TQC_I18N.written) || 'Written to Google Sheet', 'success');
          } else {
            showToast(((window.TQC_I18N && TQC_I18N.write_failed) || 'Write failed: {}').replace('{}', data.error || 'Unknown error'), 'error');
          }
        })
        .catch(function(err) {
          showToast(((window.TQC_I18N && TQC_I18N.network_error) || 'Network error: {}').replace('{}', err.message), 'error');
        });
    }},
    { label: (window.TQC_I18N && TQC_I18N.cancel) || 'Cancel', cancel: true, action: function() {} }
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
function syncRules(btn) {
  if (!btn && typeof event !== 'undefined') btn = event.target;
  if (btn) setLoading(btn, true);
  var quarter = currentQuarter();
  fetch(apiUrl('/api/sync-rules'), {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ quarter: quarter })
  })
    .then(function(r) { return r.json(); })
    .then(function(data) {
      if (btn) setLoading(btn, false);
      if (data.ok) {
        showToast((window.TQC_I18N && TQC_I18N.synced) || 'Rules synced', 'success');
        setTimeout(function() { location.reload(); }, 800);
      } else {
        showToast(((window.TQC_I18N && TQC_I18N.sync_failed) || 'Sync failed: {}').replace('{}', data.error || 'Unknown error'), 'error');
      }
    })
    .catch(function(err) {
      if (btn) setLoading(btn, false);
      showToast(((window.TQC_I18N && TQC_I18N.network_error) || 'Network error: {}').replace('{}', err.message), 'error');
    });
}
