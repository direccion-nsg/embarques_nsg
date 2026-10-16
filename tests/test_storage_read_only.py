"""Legacy cutover blocks remote writes and preserves document consultation."""

import unittest
from unittest.mock import Mock, patch

from modules import storage


class StorageReadOnlyTests(unittest.TestCase):
    def test_cutover_is_read_only_without_runtime_configuration(self):
        self.assertTrue(storage.LEGACY_STORAGE_READ_ONLY)

    def test_bucket_initialization_never_creates_a_client(self):
        with patch.object(storage, "_client") as client:
            with self.assertLogs(storage.__name__, level="WARNING") as logs:
                storage.init_storage()
            client.assert_not_called()
        self.assertIn("LEGACY_STORAGE_READ_ONLY", logs.output[0])

    def test_all_upload_entry_points_fail_before_client_or_network(self):
        for upload, filename in (
            (storage.subir_pdf, "paquete.pdf"),
            (storage.subir_pdf_combinado, "combinado.pdf"),
            (storage.subir_evidencia, "guia.jpg"),
            (storage.subir_evidencia, "guia.pdf"),
        ):
            with self.subTest(upload=upload.__name__, filename=filename):
                with patch.object(storage, "_client") as client:
                    with self.assertRaisesRegex(RuntimeError, "modo de consulta"):
                        upload(b"document content", filename)
                    client.assert_not_called()

    def test_pdf_download_remains_available(self):
        client = Mock()
        bucket = client.storage.from_.return_value
        bucket.download.return_value = b"historical pdf"
        with patch.object(storage, "_client", return_value=client):
            self.assertEqual(storage.descargar_pdf_bytes("pdfs/historico.pdf"), b"historical pdf")
        client.storage.from_.assert_called_once_with("embarques-pdfs")
        bucket.download.assert_called_once_with("pdfs/historico.pdf")
        bucket.upload.assert_not_called()

    def test_evidence_download_remains_available(self):
        client = Mock()
        bucket = client.storage.from_.return_value
        bucket.download.return_value = b"historical evidence"
        with patch.object(storage, "_client", return_value=client):
            self.assertEqual(
                storage.descargar_evidencia_bytes("evidencias/historica.jpg"),
                b"historical evidence",
            )
        client.storage.from_.assert_called_once_with("embarques-evidencias")
        bucket.download.assert_called_once_with("evidencias/historica.jpg")
        bucket.upload.assert_not_called()

    def test_signed_read_url_preserves_path_expiry_and_both_response_formats(self):
        for key in ("signedURL", "signed_url"):
            with self.subTest(key=key):
                client = Mock()
                bucket = client.storage.from_.return_value
                bucket.create_signed_url.return_value = {key: "signed-read-reference"}
                with patch.object(storage, "_client", return_value=client):
                    self.assertEqual(
                        storage.generar_url_firmada("pdfs/historico.pdf", 60),
                        "signed-read-reference",
                    )
                bucket.create_signed_url.assert_called_once_with("pdfs/historico.pdf", 60)
                bucket.upload.assert_not_called()


if __name__ == "__main__":
    unittest.main()
