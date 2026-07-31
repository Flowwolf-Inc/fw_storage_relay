from fw_storage_relay.commands.domain_migration import rename_s3_folder, update_s3_file_urls
from fw_storage_relay.commands.migrate import migrate_s3_files

commands = [migrate_s3_files, update_s3_file_urls, rename_s3_folder]
