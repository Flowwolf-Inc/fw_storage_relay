app_name = "fw_storage_relay"
app_title = "FW Storage Relay"
app_publisher = "Flowwolf Inc"
app_description = "**FW Storage Relay** moves your Frappe file attachments to AWS S3 on upload, frees up local disk, and keeps files accessible through Frappe like nothing changed."
app_email = "support@flowwolf.io"
app_license = "mit"

after_install = "fw_storage_relay.install.after_install"
after_migrate = "fw_storage_relay.install.after_migrate"

override_doctype_class = {
	"File": "fw_storage_relay.overrides.file.CustomFile",
}

doc_events = {
	"File": {
		"after_insert": "fw_storage_relay.relay.after_insert_offload",
	},
}

write_file = "fw_storage_relay.relay.write_file"
delete_file_data_content = "fw_storage_relay.relay.delete_file_data_content"

fixtures = ["Custom Field"]
