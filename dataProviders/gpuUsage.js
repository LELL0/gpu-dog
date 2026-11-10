// SPDX-License-Identifier: GPL-3.0-or-later
// GPU utilization reader shared by GPU Cat and the local Vitals patch.
//
// Supported sources (all unprivileged):
//   Intel i915 : 1 - delta(gt0/rc6_residency_ms) / delta(t)
//   Intel xe   : 1 - delta(tile0/gt0/gtidle/idle_residency_ms) / delta(t)
//   AMD amdgpu : device/gpu_busy_percent
//   NVIDIA     : nvidia-smi --query-gpu=utilization.gpu
//
// A GPU that is runtime-suspended is reported as 'off' and is never
// touched, so polling does not wake a sleeping discrete GPU.
// "Integrated" = the GPU on PCI bus 00; every other GPU counts as discrete.
import Gio from 'gi://Gio'
import GLib from 'gi://GLib'

Gio._promisify(Gio.File.prototype, 'load_contents_async')
Gio._promisify(Gio.Subprocess.prototype, 'communicate_utf8_async')

const decoder = new TextDecoder('utf-8')
const MIN_SAMPLE_MS = 500

async function readText(path) {
	const [bytes] = await Gio.File.new_for_path(path).load_contents_async(null)
	return decoder.decode(bytes).trim()
}

function readSync(path) {
	try {
		const [ok, bytes] = GLib.file_get_contents(path)
		return ok ? decoder.decode(bytes).trim() : null
	} catch (e) {
		return null
	}
}

function listDir(path) {
	const names = []
	try {
		const en = Gio.File.new_for_path(path).enumerate_children('standard::name', Gio.FileQueryInfoFlags.NONE, null)
		let info
		while ((info = en.next_file(null)) !== null)
			names.push(info.get_name())
		en.close(null)
	} catch (e) { }
	return names
}

function linkBase(path) {
	try {
		return GLib.path_get_basename(GLib.file_read_link(path))
	} catch (e) {
		return ''
	}
}

function driverName(dev) {
	try {
		const target = GLib.file_read_link(`${dev}/driver`)
		return GLib.path_get_basename(target)
	} catch (e) {
		return null
	}
}

class Gpu {
	constructor(card, dev, pciAddr, vendor, driver) {
		this.card = card
		this.dev = dev
		this.integrated = /^[0-9a-f]{4}:00:/.test(pciAddr)
		this.vendor = vendor
		this.driver = driver
		this.residencyPath = null
		this.prev = null
		this.busy = false
		this.last = null

		if (vendor === '0x8086') {
			for (const p of [
				`/sys/class/drm/${card}/gt/gt0/rc6_residency_ms`, // i915
				`/sys/class/drm/${card}/power/rc6_residency_ms`, // i915, older kernels
				`${dev}/tile0/gt0/gtidle/idle_residency_ms`, // xe
			]) {
				if (readSync(p) !== null) {
					this.residencyPath = p
					break
				}
			}
		}
	}

	get supported() {
		if (this.vendor === '0x8086')
			return this.residencyPath !== null
		if (this.vendor === '0x1002')
			return readSync(`${this.dev}/gpu_busy_percent`) !== null || this.driver === 'amdgpu'
		if (this.vendor === '0x10de')
			return GLib.find_program_in_path('nvidia-smi') !== null
		return false
	}

	async isAwake() {
		try {
			const status = await readText(`${this.dev}/power/runtime_status`)
			return status === 'active'
		} catch (e) {
			return true // runtime PM not exposed: device is always on
		}
	}

	// fraction 0..1, 'off', or null (no value yet / error)
	async sample() {
		if (!(await this.isAwake()))
			return 'off'
		if (!Gio.File.new_for_path(`${this.dev}/driver`).query_exists(null))
			return 'off'
		try {
			if (this.vendor === '0x8086')
				return await this._sampleResidency()
			if (this.vendor === '0x1002')
				return clamp(parseFloat(await readText(`${this.dev}/gpu_busy_percent`)) / 100)
			if (this.vendor === '0x10de')
				return await this._sampleNvidia()
		} catch (e) { }
		return null
	}

	async _sampleResidency() {
		const idleMs = parseInt(await readText(this.residencyPath))
		const now = GLib.get_monotonic_time() / 1000
		const prev = this.prev
		if (prev && now - prev.now < MIN_SAMPLE_MS)
			return this.last
		this.prev = { idleMs, now }
		if (!prev)
			return null
		this.last = clamp(1 - (idleMs - prev.idleMs) / (now - prev.now))
		return this.last
	}

	async _sampleNvidia() {
		if (this.busy)
			return this.last
		this.busy = true
		try {
			const proc = Gio.Subprocess.new(
				['nvidia-smi', `--id=${this.pciBusId()}`, '--query-gpu=utilization.gpu', '--format=csv,noheader,nounits'],
				Gio.SubprocessFlags.STDOUT_PIPE | Gio.SubprocessFlags.STDERR_SILENCE)
			const [out] = await proc.communicate_utf8_async(null, null)
			const v = parseFloat(out)
			this.last = Number.isFinite(v) ? clamp(v / 100) : null
			return this.last
		} finally {
			this.busy = false
		}
	}

	pciBusId() {
		return linkBase(this.dev)
	}
}

function clamp(v) {
	return Number.isFinite(v) ? Math.min(1, Math.max(0, v)) : null
}

export class GpuUsage {
	constructor() {
		this.gpus = []
		for (const card of listDir('/sys/class/drm')) {
			if (!/^card\d+$/.test(card))
				continue
			const dev = `/sys/class/drm/${card}/device`
			const vendor = readSync(`${dev}/vendor`)
			if (!vendor)
				continue
			const gpu = new Gpu(card, dev, linkBase(dev), vendor, driverName(dev))
			if (gpu.supported)
				this.gpus.push(gpu)
		}
	}

	get hasIgpu() { return this.gpus.some(g => g.integrated) }
	get hasDgpu() { return this.gpus.some(g => !g.integrated) }

	// Highest value among the matching GPUs; 'off' if all of them sleep;
	// null if none exist or none produced a value yet.
	async _group(integrated) {
		const gpus = this.gpus.filter(g => g.integrated === integrated)
		if (gpus.length === 0)
			return null
		const vals = await Promise.all(gpus.map(g => g.sample()))
		const nums = vals.filter(v => typeof v === 'number')
		if (nums.length)
			return Math.max(...nums)
		return vals.every(v => v === 'off') ? 'off' : null
	}

	igpu() { return this._group(true) }
	dgpu() { return this._group(false) }

	// max over all GPUs, 0..1 (sleeping GPUs count as 0)
	async total() {
		const vals = await Promise.all(this.gpus.map(g => g.sample()))
		const nums = vals.filter(v => typeof v === 'number')
		return nums.length ? Math.max(...nums) : 0
	}
}
