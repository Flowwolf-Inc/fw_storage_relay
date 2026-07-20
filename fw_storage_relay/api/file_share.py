# Copyright (c) 2026, Flowwolf Inc. and contributors
# For license information, please see license.txt

import frappe


@frappe.whitelist()
def get_file_share_info(file_name: str):
	return frappe.get_doc("File", file_name).get_file_share_info()


@frappe.whitelist()
def generate_file_share_key(file_name: str):
	result = frappe.get_doc("File", file_name).generate_file_share_key()
	frappe.db.commit()
	return result


@frappe.whitelist()
def reset_file_share_key(file_name: str):
	result = frappe.get_doc("File", file_name).reset_file_share_key()
	frappe.db.commit()
	return result


@frappe.whitelist()
def regenerate_file_share_key(file_name: str):
	result = frappe.get_doc("File", file_name).regenerate_file_share_key()
	frappe.db.commit()
	return result


@frappe.whitelist()
def revoke_file_share_key(file_name: str):
	result = frappe.get_doc("File", file_name).revoke_file_share_key()
	frappe.db.commit()
	return result
