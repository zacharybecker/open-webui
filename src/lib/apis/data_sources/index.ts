/// <reference lib="esnext" />
import { WEBUI_API_BASE_URL } from '$lib/constants';

// Types
export interface DataSourceType {
	id: string;
	name: string;
	description: string;
	icon: string;
	config_schema: Record<string, unknown>;
	credentials_schema: Record<string, unknown>;
	supports_webhooks: boolean;
}

export interface DataSource {
	id: string;
	knowledge_id: string;
	user_id: string;
	source_type: string;
	name: string;
	config: Record<string, unknown> | null;
	sync_config: Record<string, unknown> | null;
	status: string;
	last_sync_at: number | null;
	last_sync_error: string | null;
	created_at: number;
	updated_at: number;
}

export interface DataSourceListResponse {
	items: DataSource[];
	total: number;
}

export interface SourceInfo {
	id: string;
	name: string;
	description: string | null;
	url: string | null;
	metadata: Record<string, unknown> | null;
}

export interface ValidateCredentialsResponse {
	valid: boolean;
	message: string | null;
	user_info: Record<string, unknown> | null;
}

export interface SyncResult {
	success: boolean;
	files_synced: number;
	files_updated: number;
	files_deleted: number;
	errors: string[];
	duration_seconds: number;
}

export interface SyncStatus {
	status: string;
	last_sync_at: number | null;
	last_sync_error: string | null;
}

// API Functions

export const getDataSourceTypes = async (token: string): Promise<DataSourceType[]> => {
	let error = null;

	const res = await fetch(`${WEBUI_API_BASE_URL}/data_sources/types`, {
		method: 'GET',
		headers: {
			Accept: 'application/json',
			'Content-Type': 'application/json',
			authorization: `Bearer ${token}`
		}
	})
		.then(async (res) => {
			if (!res.ok) throw await res.json();
			return res.json();
		})
		.catch((err) => {
			error = err.detail;
			console.error(err);
			return null;
		});

	if (error) {
		throw error;
	}

	return res;
};

export const getDataSourcesByKnowledgeId = async (
	token: string,
	knowledgeId: string
): Promise<DataSourceListResponse> => {
	let error = null;

	const res = await fetch(`${WEBUI_API_BASE_URL}/data_sources/knowledge/${knowledgeId}`, {
		method: 'GET',
		headers: {
			Accept: 'application/json',
			'Content-Type': 'application/json',
			authorization: `Bearer ${token}`
		}
	})
		.then(async (res) => {
			if (!res.ok) throw await res.json();
			return res.json();
		})
		.catch((err) => {
			error = err.detail;
			console.error(err);
			return null;
		});

	if (error) {
		throw error;
	}

	return res;
};

export const createDataSource = async (
	token: string,
	data: {
		knowledge_id: string;
		source_type: string;
		name: string;
		config?: Record<string, unknown>;
		credentials?: Record<string, unknown>;
		sync_config?: Record<string, unknown>;
	}
): Promise<DataSource> => {
	let error = null;

	const res = await fetch(`${WEBUI_API_BASE_URL}/data_sources/create`, {
		method: 'POST',
		headers: {
			Accept: 'application/json',
			'Content-Type': 'application/json',
			authorization: `Bearer ${token}`
		},
		body: JSON.stringify(data)
	})
		.then(async (res) => {
			if (!res.ok) throw await res.json();
			return res.json();
		})
		.catch((err) => {
			error = err.detail;
			console.error(err);
			return null;
		});

	if (error) {
		throw error;
	}

	return res;
};

export const getDataSourceById = async (token: string, id: string): Promise<DataSource> => {
	let error = null;

	const res = await fetch(`${WEBUI_API_BASE_URL}/data_sources/${id}`, {
		method: 'GET',
		headers: {
			Accept: 'application/json',
			'Content-Type': 'application/json',
			authorization: `Bearer ${token}`
		}
	})
		.then(async (res) => {
			if (!res.ok) throw await res.json();
			return res.json();
		})
		.catch((err) => {
			error = err.detail;
			console.error(err);
			return null;
		});

	if (error) {
		throw error;
	}

	return res;
};

export const updateDataSource = async (
	token: string,
	id: string,
	data: {
		name?: string;
		config?: Record<string, unknown>;
		credentials?: Record<string, unknown>;
		sync_config?: Record<string, unknown>;
	}
): Promise<DataSource> => {
	let error = null;

	const res = await fetch(`${WEBUI_API_BASE_URL}/data_sources/${id}/update`, {
		method: 'POST',
		headers: {
			Accept: 'application/json',
			'Content-Type': 'application/json',
			authorization: `Bearer ${token}`
		},
		body: JSON.stringify(data)
	})
		.then(async (res) => {
			if (!res.ok) throw await res.json();
			return res.json();
		})
		.catch((err) => {
			error = err.detail;
			console.error(err);
			return null;
		});

	if (error) {
		throw error;
	}

	return res;
};

export const deleteDataSource = async (token: string, id: string): Promise<boolean> => {
	let error = null;

	const res = await fetch(`${WEBUI_API_BASE_URL}/data_sources/${id}`, {
		method: 'DELETE',
		headers: {
			Accept: 'application/json',
			'Content-Type': 'application/json',
			authorization: `Bearer ${token}`
		}
	})
		.then(async (res) => {
			if (!res.ok) throw await res.json();
			return res.json();
		})
		.catch((err) => {
			error = err.detail;
			console.error(err);
			return null;
		});

	if (error) {
		throw error;
	}

	return res;
};

export const validateDataSourceCredentials = async (
	token: string,
	sourceType: string,
	credentials: Record<string, unknown>
): Promise<ValidateCredentialsResponse> => {
	let error = null;

	const res = await fetch(`${WEBUI_API_BASE_URL}/data_sources/validate`, {
		method: 'POST',
		headers: {
			Accept: 'application/json',
			'Content-Type': 'application/json',
			authorization: `Bearer ${token}`
		},
		body: JSON.stringify({
			source_type: sourceType,
			credentials: credentials
		})
	})
		.then(async (res) => {
			if (!res.ok) throw await res.json();
			return res.json();
		})
		.catch((err) => {
			error = err.detail;
			console.error(err);
			return null;
		});

	if (error) {
		throw error;
	}

	return res;
};

export const listAvailableSources = async (
	token: string,
	sourceType: string,
	credentials: Record<string, unknown>,
	search?: string
): Promise<SourceInfo[]> => {
	let error = null;

	const res = await fetch(`${WEBUI_API_BASE_URL}/data_sources/sources`, {
		method: 'POST',
		headers: {
			Accept: 'application/json',
			'Content-Type': 'application/json',
			authorization: `Bearer ${token}`
		},
		body: JSON.stringify({
			source_type: sourceType,
			credentials: credentials,
			search: search || null
		})
	})
		.then(async (res) => {
			if (!res.ok) throw await res.json();
			return res.json();
		})
		.catch((err) => {
			error = err.detail;
			console.error(err);
			return null;
		});

	if (error) {
		throw error;
	}

	return res;
};

export const syncDataSource = async (token: string, id: string): Promise<SyncResult> => {
	let error = null;

	const res = await fetch(`${WEBUI_API_BASE_URL}/data_sources/${id}/sync`, {
		method: 'POST',
		headers: {
			Accept: 'application/json',
			'Content-Type': 'application/json',
			authorization: `Bearer ${token}`
		}
	})
		.then(async (res) => {
			if (!res.ok) throw await res.json();
			return res.json();
		})
		.catch((err) => {
			error = err.detail;
			console.error(err);
			return null;
		});

	if (error) {
		throw error;
	}

	return res;
};

export const getDataSourceSyncStatus = async (token: string, id: string): Promise<SyncStatus> => {
	let error = null;

	const res = await fetch(`${WEBUI_API_BASE_URL}/data_sources/${id}/status`, {
		method: 'GET',
		headers: {
			Accept: 'application/json',
			'Content-Type': 'application/json',
			authorization: `Bearer ${token}`
		}
	})
		.then(async (res) => {
			if (!res.ok) throw await res.json();
			return res.json();
		})
		.catch((err) => {
			error = err.detail;
			console.error(err);
			return null;
		});

	if (error) {
		throw error;
	}

	return res;
};
