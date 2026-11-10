import { GpuUsage } from './gpuUsage.js'

export const MAX_CPU_UTILIZATION = 1.0

// Yields the busiest GPU's utilization in [0, 1]. Sleeping GPUs are never woken.
export default async function* () {
	const gpu = new GpuUsage()
	await gpu.total() // prime residency baselines
	while (true)
		yield await gpu.total()
}
