"""Sprint 5 — Enhanced Audit Log: pencatatan akses data rekonsiliasi.

Sebelumnya audit log hanya mencatat operasi write (insert/update/delete).
Test ini memverifikasi bahwa sistem kini mencatat SIAPA yang mengakses
data rekonsiliasi dan KAPAN, termasuk throttling agar polling dashboard
tidak membanjiri audit log.
"""
import json
import os
from unittest.mock import patch, MagicMock

import app as app_module
from app import app as flask_app, log_data_access, write_audit


def _request_ctx_with_user(user):
    ctx = flask_app.test_request_context('/')
    ctx.push()
    from flask import g
    g.current_user = user
    return ctx


class TestLogDataAccess:
    def setup_method(self):
        app_module._ACCESS_LOG_SEEN.clear()

    def test_records_actor_and_resource(self):
        ctx = _request_ctx_with_user(
            {'id': 'u1', 'email': 'pengawas@ojk.go.id', 'role': 'pengawas'})
        try:
            with patch('app.write_audit') as mock_audit:
                log_data_access('snapshot rekonsiliasi terbaru (/api/reconciliation/latest)', '3 PAKD')
                assert mock_audit.call_count == 1
                args, kwargs = mock_audit.call_args
                assert args[0] == 'AKSES DATA'
                assert 'pengawas@ojk.go.id' in args[1]
                assert '(pengawas)' in args[1]
                assert 'mengakses' in args[1]
                assert '3 PAKD' in args[1]
                assert kwargs['actor'] == {'email': 'pengawas@ojk.go.id', 'role': 'pengawas'}
        finally:
            ctx.pop()

    def test_repeated_access_same_user_throttled(self):
        ctx = _request_ctx_with_user(
            {'id': 'u1', 'email': 'pengawas@ojk.go.id', 'role': 'pengawas'})
        try:
            with patch('app.write_audit') as mock_audit:
                log_data_access('riwayat rekonsiliasi (/api/reconciliation-history)')
                log_data_access('riwayat rekonsiliasi (/api/reconciliation-history)')
                assert mock_audit.call_count == 1
        finally:
            ctx.pop()

    def test_different_users_logged_separately(self):
        with patch('app.write_audit') as mock_audit:
            ctx = _request_ctx_with_user(
                {'id': 'u1', 'email': 'a@ojk.go.id', 'role': 'pengawas'})
            try:
                log_data_access('riwayat rekonsiliasi (/api/reconciliation-history)')
            finally:
                ctx.pop()
            ctx = _request_ctx_with_user(
                {'id': 'u2', 'email': 'b@pakd.co.id', 'role': 'pakd'})
            try:
                log_data_access('riwayat rekonsiliasi (/api/reconciliation-history)')
            finally:
                ctx.pop()
            assert mock_audit.call_count == 2

    def test_noop_outside_request_context(self):
        with patch('app.write_audit') as mock_audit:
            log_data_access('riwayat rekonsiliasi')
            assert mock_audit.call_count == 0


class TestWriteAuditActor:
    def test_file_fallback_includes_actor(self, tmp_path):
        audit_file = str(tmp_path / 'audit_log.json')
        with patch.object(app_module, 'AUDIT_FILE', audit_file), \
             patch('app._get_db_conn', return_value=None):
            write_audit('AKSES DATA', 'x mengakses y',
                        actor={'email': 'x@ojk.go.id', 'role': 'pengawas'})
        with open(audit_file) as f:
            logs = json.load(f)
        assert logs[0]['aktor'] == 'x@ojk.go.id'
        assert logs[0]['aktor_role'] == 'pengawas'

    def test_actor_auto_detected_from_request_context(self, tmp_path):
        audit_file = str(tmp_path / 'audit_log.json')
        ctx = _request_ctx_with_user(
            {'id': 'u9', 'email': 'auto@ojk.go.id', 'role': 'super_admin'})
        try:
            with patch.object(app_module, 'AUDIT_FILE', audit_file), \
                 patch('app._get_db_conn', return_value=None):
                write_audit('UPDATE_PAKD', 'Edit PAKD-001')
        finally:
            ctx.pop()
        with open(audit_file) as f:
            logs = json.load(f)
        assert logs[0]['aktor'] == 'auto@ojk.go.id'
        assert logs[0]['aktor_role'] == 'super_admin'


class TestReconciliationEndpointsAudit:
    def setup_method(self):
        app_module._ACCESS_LOG_SEEN.clear()

    def test_history_endpoint_logs_access(self, client):
        fake_conn = MagicMock()
        fake_cur = fake_conn.cursor.return_value
        fake_cur.fetchall.return_value = []
        with patch('app._get_db_conn', return_value=fake_conn), \
             patch('app._return_db_conn'), \
             patch('app.write_audit') as mock_audit:
            resp = client.get('/api/reconciliation-history')
            assert resp.status_code == 200
            access_calls = [c for c in mock_audit.call_args_list
                            if c.args[0] == 'AKSES DATA']
            assert len(access_calls) == 1
            assert '/api/reconciliation-history' in access_calls[0].args[1]

    def test_audit_log_endpoint_returns_actor_fields(self, client):
        fake_conn = MagicMock()
        fake_cur = fake_conn.cursor.return_value
        fake_cur.fetchall.return_value = [
            ('07 Jul 2026, 10:00', 'AKSES DATA',
             'pengawas@ojk.go.id (pengawas) mengakses snapshot rekonsiliasi',
             'pengawas@ojk.go.id', 'pengawas'),
        ]
        with patch('app._get_db_conn', return_value=fake_conn), \
             patch('app._return_db_conn'):
            resp = client.get('/api/audit-log')
            assert resp.status_code == 200
            data = resp.get_json()['data']
            assert data[0]['aktor'] == 'pengawas@ojk.go.id'
            assert data[0]['aktor_role'] == 'pengawas'
