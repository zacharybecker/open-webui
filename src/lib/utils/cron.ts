export function isValidCronExpression(expression: string): boolean {
	const parts = expression.trim().split(/\s+/);
	if (parts.length !== 5) return false;

	return (
		isValidCronField(parts[0], 0, 59) &&
		isValidCronField(parts[1], 0, 23) &&
		isValidCronField(parts[2], 1, 31) &&
		isValidCronField(parts[3], 1, 12) &&
		isValidCronField(parts[4], 0, 7, true)
	);
}

function isValidCronField(
	field: string,
	min: number,
	max: number,
	allowSeven: boolean = false
): boolean {
	const parts = field.split(',');
	return parts.every((part) => isValidCronPart(part, min, max, allowSeven));
}

function isValidCronPart(
	part: string,
	min: number,
	max: number,
	allowSeven: boolean
): boolean {
	if (part === '*') return true;

	const [base, step] = part.split('/');
	if (step !== undefined && !isValidCronNumber(step, 1, max)) {
		return false;
	}

	if (base === '*') return true;

	if (base.includes('-')) {
		const [start, end] = base.split('-');
		return (
			isValidCronNumber(start, min, max, allowSeven) &&
			isValidCronNumber(end, min, max, allowSeven) &&
			parseInt(start, 10) <= parseInt(end, 10)
		);
	}

	return isValidCronNumber(base, min, max, allowSeven);
}

function isValidCronNumber(
	value: string,
	min: number,
	max: number,
	allowSeven: boolean = false
): boolean {
	if (!/^\d+$/.test(value)) return false;
	const numberValue = parseInt(value, 10);
	if (allowSeven && numberValue === 7) return true;
	return numberValue >= min && numberValue <= max;
}
