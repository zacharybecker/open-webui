<script lang="ts">
	import { toast } from 'svelte-sonner';
	import { createEventDispatcher, getContext, onMount } from 'svelte';
	const i18n = getContext('i18n');
	const dispatch = createEventDispatcher();

	import Modal from '$lib/components/common/Modal.svelte';
	import Spinner from '$lib/components/common/Spinner.svelte';
	import {
		getDataSourceTypes,
		validateDataSourceCredentials,
		listAvailableSources,
		createDataSource,
		type DataSourceType,
		type SourceInfo
	} from '$lib/apis/data_sources';

	export let show = false;
	export let knowledgeId: string;

	let step: 'select-type' | 'configure' | 'select-source' = 'select-type';
	let loading = false;
	let validating = false;
	let loadingSources = false;

	let sourceTypes: DataSourceType[] = [];
	let selectedType: DataSourceType | null = null;
	let availableSources: SourceInfo[] = [];
	let selectedSource: SourceInfo | null = null;

	// Form data
	let name = '';
	let credentials: Record<string, string> = {};
	let syncMode = 'manual';

	// Reset state when modal opens
	$: if (show) {
		resetState();
		loadSourceTypes();
	}

	function resetState() {
		step = 'select-type';
		selectedType = null;
		selectedSource = null;
		availableSources = [];
		name = '';
		credentials = {};
		syncMode = 'manual';
	}

	async function loadSourceTypes() {
		loading = true;
		try {
			sourceTypes = await getDataSourceTypes(localStorage.token);
		} catch (e) {
			toast.error(`Failed to load source types: ${e}`);
		} finally {
			loading = false;
		}
	}

	function selectType(type: DataSourceType) {
		selectedType = type;
		// Initialize credentials object based on schema
		credentials = {};
		const props = type.credentials_schema?.properties || {};
		for (const key of Object.keys(props)) {
			credentials[key] = '';
		}
		step = 'configure';
	}

	async function validateAndLoadSources() {
		if (!selectedType) return;

		validating = true;
		try {
			const result = await validateDataSourceCredentials(
				localStorage.token,
				selectedType.id,
				credentials
			);

			if (result.valid) {
				toast.success(result.message || $i18n.t('Credentials validated successfully'));

				// Load available sources
				loadingSources = true;
				try {
					availableSources = await listAvailableSources(
						localStorage.token,
						selectedType.id,
						credentials
					);
					step = 'select-source';
				} catch (e) {
					toast.error(`Failed to load sources: ${e}`);
				} finally {
					loadingSources = false;
				}
			} else {
				toast.error(result.message || $i18n.t('Invalid credentials'));
			}
		} catch (e) {
			toast.error(`Validation failed: ${e}`);
		} finally {
			validating = false;
		}
	}

	function selectSource(source: SourceInfo) {
		selectedSource = source;
		if (!name) {
			name = source.name;
		}
	}

	async function handleSubmit() {
		if (!selectedType || !selectedSource) return;

		loading = true;
		try {
			// Build config based on source type
			const config: Record<string, unknown> = {};
			if (selectedType.id === 'confluence') {
				config.space_key = selectedSource.id;
			} else if (selectedType.id === 'jira') {
				config.project_key = selectedSource.id;
			} else if (selectedType.id === 'github') {
				config.repository = selectedSource.id;
			}

			const dataSource = await createDataSource(localStorage.token, {
				knowledge_id: knowledgeId,
				source_type: selectedType.id,
				name: name,
				config: config,
				credentials: credentials,
				sync_config: { sync_mode: syncMode }
			});

			toast.success($i18n.t('Data source created successfully'));
			dispatch('created', dataSource);
			show = false;
		} catch (e) {
			toast.error(`Failed to create data source: ${e}`);
		} finally {
			loading = false;
		}
	}

	function getSourceTypeIcon(typeId: string): string {
		const icons: Record<string, string> = {
			confluence:
				'M2.5 19.7c-.2-.4-.1-.9.2-1.2l6.4-8.5c.1-.1.1-.3 0-.4L3.4 2.2c-.3-.3-.4-.8-.2-1.2.2-.4.6-.6 1-.6h5.3c.4 0 .7.2.9.5l5.5 7.5c.1.2.4.2.5 0l5.5-7.5c.2-.3.5-.5.9-.5h5.3c.4 0 .8.2 1 .6.2.4.1.9-.2 1.2l-5.7 7.4c-.1.1-.1.3 0 .4l6.4 8.5c.3.3.4.8.2 1.2-.2.4-.6.6-1 .6h-5.3c-.4 0-.7-.2-.9-.5l-6.1-8.2c-.1-.2-.4-.2-.5 0l-6.1 8.2c-.2.3-.5.5-.9.5H3.5c-.4 0-.8-.2-1-.6z',
			jira: 'M11.53.69a2.19 2.19 0 0 1 .94 0l9.63 2.25a2.2 2.2 0 0 1 1.67 2.12v9.88a2.2 2.2 0 0 1-1.67 2.12l-9.63 2.25a2.19 2.19 0 0 1-.94 0l-9.63-2.25A2.2 2.2 0 0 1 .23 14.94V5.06a2.2 2.2 0 0 1 1.67-2.12L11.53.69z',
			github:
				'M12 0c-6.626 0-12 5.373-12 12 0 5.302 3.438 9.8 8.207 11.387.599.111.793-.261.793-.577v-2.234c-3.338.726-4.033-1.416-4.033-1.416-.546-1.387-1.333-1.756-1.333-1.756-1.089-.745.083-.729.083-.729 1.205.084 1.839 1.237 1.839 1.237 1.07 1.834 2.807 1.304 3.492.997.107-.775.418-1.305.762-1.604-2.665-.305-5.467-1.334-5.467-5.931 0-1.311.469-2.381 1.236-3.221-.124-.303-.535-1.524.117-3.176 0 0 1.008-.322 3.301 1.23.957-.266 1.983-.399 3.003-.404 1.02.005 2.047.138 3.006.404 2.291-1.552 3.297-1.23 3.297-1.23.653 1.653.242 2.874.118 3.176.77.84 1.235 1.911 1.235 3.221 0 4.609-2.807 5.624-5.479 5.921.43.372.823 1.102.823 2.222v3.293c0 .319.192.694.801.576 4.765-1.589 8.199-6.086 8.199-11.386 0-6.627-5.373-12-12-12z'
		};
		return icons[typeId] || '';
	}

	function getFieldLabel(key: string, schema: Record<string, unknown>): string {
		const props = schema?.properties as Record<string, Record<string, string>> || {};
		return props[key]?.title || key;
	}

	function getFieldDescription(key: string, schema: Record<string, unknown>): string {
		const props = schema?.properties as Record<string, Record<string, string>> || {};
		return props[key]?.description || '';
	}

	function isFieldRequired(key: string, schema: Record<string, unknown>): boolean {
		const required = schema?.required as string[] || [];
		return required.includes(key);
	}

	function getFieldType(key: string, schema: Record<string, unknown>): string {
		const props = schema?.properties as Record<string, Record<string, string>> || {};
		return props[key]?.format === 'password' ? 'password' : 'text';
	}
</script>

<Modal size="md" bind:show>
	<div class="px-6 py-5">
		<!-- Header -->
		<div class="flex items-center justify-between mb-6">
			<h2 class="text-xl font-semibold">
				{#if step === 'select-type'}
					{$i18n.t('Add External Data Source')}
				{:else if step === 'configure'}
					{$i18n.t('Configure')} {selectedType?.name}
				{:else}
					{$i18n.t('Select Source')}
				{/if}
			</h2>
			<button
				class="text-gray-400 hover:text-gray-600 dark:hover:text-gray-300"
				on:click={() => (show = false)}
			>
				<svg class="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
					<path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M6 18L18 6M6 6l12 12" />
				</svg>
			</button>
		</div>

		{#if loading}
			<div class="flex justify-center py-8">
				<Spinner className="size-6" />
			</div>
		{:else if step === 'select-type'}
			<!-- Source Type Selection -->
			<div class="grid grid-cols-1 gap-3">
				{#each sourceTypes as type}
					<button
						class="flex items-center gap-4 p-4 border border-gray-200 dark:border-gray-700 rounded-xl hover:bg-gray-50 dark:hover:bg-gray-800 transition text-left"
						on:click={() => selectType(type)}
					>
						<div class="w-10 h-10 flex items-center justify-center bg-gray-100 dark:bg-gray-700 rounded-lg">
							<svg class="w-6 h-6" viewBox="0 0 24 24" fill="currentColor">
								<path d={getSourceTypeIcon(type.id)} />
							</svg>
						</div>
						<div class="flex-1">
							<div class="font-medium">{type.name}</div>
							<div class="text-sm text-gray-500 dark:text-gray-400">{type.description}</div>
						</div>
						<svg class="w-5 h-5 text-gray-400" fill="none" stroke="currentColor" viewBox="0 0 24 24">
							<path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M9 5l7 7-7 7" />
						</svg>
					</button>
				{/each}
			</div>
		{:else if step === 'configure'}
			<!-- Credentials Configuration -->
			<div class="space-y-4">
				<button
					class="flex items-center gap-2 text-sm text-gray-500 hover:text-gray-700 dark:hover:text-gray-300"
					on:click={() => (step = 'select-type')}
				>
					<svg class="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
						<path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M15 19l-7-7 7-7" />
					</svg>
					{$i18n.t('Back')}
				</button>

				{#if selectedType}
					{@const schema = selectedType.credentials_schema}
					{@const props = schema?.properties || {}}
					{#each Object.keys(props) as key}
						<div>
							<label class="block text-sm font-medium mb-1">
								{getFieldLabel(key, schema)}
								{#if isFieldRequired(key, schema)}
									<span class="text-red-500">*</span>
								{/if}
							</label>
							<input
								type={getFieldType(key, schema)}
								class="w-full px-3 py-2 border border-gray-300 dark:border-gray-600 rounded-lg bg-white dark:bg-gray-800 focus:ring-2 focus:ring-blue-500 focus:border-transparent"
								placeholder={getFieldDescription(key, schema)}
								bind:value={credentials[key]}
							/>
							{#if getFieldDescription(key, schema)}
								<p class="text-xs text-gray-500 mt-1">{getFieldDescription(key, schema)}</p>
							{/if}
						</div>
					{/each}
				{/if}

				<div class="pt-4">
					<button
						class="w-full py-2.5 bg-blue-600 hover:bg-blue-700 text-white font-medium rounded-lg transition flex items-center justify-center gap-2 disabled:opacity-50 disabled:cursor-not-allowed"
						disabled={validating}
						on:click={validateAndLoadSources}
					>
						{#if validating}
							<Spinner className="size-4" />
							{$i18n.t('Validating...')}
						{:else}
							{$i18n.t('Validate & Continue')}
						{/if}
					</button>
				</div>
			</div>
		{:else if step === 'select-source'}
			<!-- Source Selection -->
			<div class="space-y-4">
				<button
					class="flex items-center gap-2 text-sm text-gray-500 hover:text-gray-700 dark:hover:text-gray-300"
					on:click={() => (step = 'configure')}
				>
					<svg class="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
						<path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M15 19l-7-7 7-7" />
					</svg>
					{$i18n.t('Back')}
				</button>

				<!-- Name input -->
				<div>
					<label class="block text-sm font-medium mb-1">{$i18n.t('Name')}</label>
					<input
						type="text"
						class="w-full px-3 py-2 border border-gray-300 dark:border-gray-600 rounded-lg bg-white dark:bg-gray-800 focus:ring-2 focus:ring-blue-500 focus:border-transparent"
						placeholder={$i18n.t('Data source name')}
						bind:value={name}
					/>
				</div>

				<!-- Source selection -->
				<div>
					<label class="block text-sm font-medium mb-2">
						{$i18n.t('Select')} {selectedType?.name} {$i18n.t('Source')}
					</label>
					<div class="max-h-60 overflow-y-auto border border-gray-200 dark:border-gray-700 rounded-lg">
						{#if loadingSources}
							<div class="flex justify-center py-8">
								<Spinner className="size-5" />
							</div>
						{:else if availableSources.length === 0}
							<div class="text-center py-8 text-gray-500">
								{$i18n.t('No sources found')}
							</div>
						{:else}
							{#each availableSources as source}
								<button
									class="w-full flex items-center gap-3 p-3 hover:bg-gray-50 dark:hover:bg-gray-800 border-b border-gray-100 dark:border-gray-700 last:border-b-0 text-left {selectedSource?.id === source.id ? 'bg-blue-50 dark:bg-blue-900/20' : ''}"
									on:click={() => selectSource(source)}
								>
									<div class="flex-1 min-w-0">
										<div class="font-medium truncate">{source.name}</div>
										{#if source.description}
											<div class="text-xs text-gray-500 truncate">{source.description}</div>
										{/if}
									</div>
									{#if selectedSource?.id === source.id}
										<svg class="w-5 h-5 text-blue-600" fill="currentColor" viewBox="0 0 20 20">
											<path fill-rule="evenodd" d="M16.707 5.293a1 1 0 010 1.414l-8 8a1 1 0 01-1.414 0l-4-4a1 1 0 011.414-1.414L8 12.586l7.293-7.293a1 1 0 011.414 0z" clip-rule="evenodd" />
										</svg>
									{/if}
								</button>
							{/each}
						{/if}
					</div>
				</div>

				<!-- Sync mode -->
				<div>
					<label class="block text-sm font-medium mb-2">{$i18n.t('Sync Schedule')}</label>
					<select
						class="w-full px-3 py-2 border border-gray-300 dark:border-gray-600 rounded-lg bg-white dark:bg-gray-800 focus:ring-2 focus:ring-blue-500 focus:border-transparent"
						bind:value={syncMode}
					>
						<option value="manual">{$i18n.t('Manual only')}</option>
						<option value="hourly">{$i18n.t('Every hour')}</option>
						<option value="every_6_hours">{$i18n.t('Every 6 hours')}</option>
						<option value="every_12_hours">{$i18n.t('Every 12 hours')}</option>
						<option value="daily">{$i18n.t('Daily')}</option>
						<option value="weekly">{$i18n.t('Weekly')}</option>
					</select>
				</div>

				<div class="pt-4">
					<button
						class="w-full py-2.5 bg-blue-600 hover:bg-blue-700 text-white font-medium rounded-lg transition flex items-center justify-center gap-2 disabled:opacity-50 disabled:cursor-not-allowed"
						disabled={loading || !selectedSource || !name.trim()}
						on:click={handleSubmit}
					>
						{#if loading}
							<Spinner className="size-4" />
							{$i18n.t('Creating...')}
						{:else}
							{$i18n.t('Create Data Source')}
						{/if}
					</button>
				</div>
			</div>
		{/if}
	</div>
</Modal>
