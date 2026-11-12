import Clutter from 'gi://Clutter'
import Gio from 'gi://Gio'
import GObject from 'gi://GObject'
import GLib from 'gi://GLib'
import St from 'gi://St'
import * as Main from 'resource:///org/gnome/shell/ui/main.js'
import * as PanelMenu from 'resource:///org/gnome/shell/ui/panelMenu.js'
import { trySpawnCommandLine } from 'resource:///org/gnome/shell/misc/util.js'
import { PopupSeparatorMenuItem } from 'resource:///org/gnome/shell/ui/popupMenu.js'
import { gettext as _ } from 'resource:///org/gnome/shell/extensions/extension.js'
import { LOG_PREFIX, SYSTEM_MONITOR_COMMAND, displayingItemNickToValue, SettingsSchemaKeys, ReactiveProperties } from './constants.js'
import { IDLE_ANIMATION_CYCLE_DURATION_MS, getAnimationCycleDurationMs, createAnimationTicker } from './math.js'
import { formatNumber, getSpritesPack, resolveColor } from './utils.js'
import createCpuGenerator, { MAX_CPU_UTILIZATION } from './dataProviders/gpu.js'


export default class GpuCatIndicator extends PanelMenu.Button {
	static {
		GObject.registerClass({
			GTypeName: 'GpuCatIndicator',
			Properties: {
				cpuUsage: GObject.ParamSpec.float('cpuUsage', 'GPU usage', 'Latest GPU utilization in [0, 1], sampled every 3 seconds', GObject.ParamFlags.READWRITE | GObject.ParamFlags.CONSTRUCT, 0, 1, 0),
				currentSpriteFrame: GObject.ParamSpec.object('currentSpriteFrame', 'Current sprite frame', 'Sprite currently displayed for the character state', GObject.ParamFlags.READWRITE | GObject.ParamFlags.CONSTRUCT, Gio.Icon),
				displayingItems: GObject.ParamSpec.jsobject('displayingItems', 'Displaying items', 'Which elements to show: the character and/or the GPU percentage', GObject.ParamFlags.READWRITE | GObject.ParamFlags.CONSTRUCT),
				isSpeedInverted: GObject.ParamSpec.boolean('isSpeedInverted', 'Invert speed', 'When true, the animation speed is inverted and the character is always active', GObject.ParamFlags.READWRITE | GObject.ParamFlags.CONSTRUCT, false),
				idleThreshold: GObject.ParamSpec.int('idleThreshold', 'Idle threshold', 'GPU percentage below which the character is considered idle (0-100)', GObject.ParamFlags.READWRITE | GObject.ParamFlags.CONSTRUCT, 0, 100, 0),
				isAnimationSmoothingEnabled: GObject.ParamSpec.boolean('isAnimationSmoothingEnabled', 'Smooth speed changes', 'When true, running speed adapts to GPU load gradually', GObject.ParamFlags.READWRITE | GObject.ParamFlags.CONSTRUCT, true),
			},
		}, this)
	}
	extension
	settings
	sprites
	animationTimeoutId = null
	refreshDataTimeoutId
	displayingItemsHandlerId
	colorHandlerId
	characterHandlerId
	updateAnimationState = null
	icon

	constructor(extension) {
		super(0.5, 'GpuCat', false)
		this.extension = extension
		this.settings = extension.getSettings()
		this.sprites = getSpritesPack(this.extension.path, this.settings.get_string(SettingsSchemaKeys.CHARACTER))
		this.initSettingsListeners()
		this.initDataRefreshSource()
		this.initUi()
	}

	get characterState() {
		if (this.isSpeedInverted) {
			return 'active'
		}


		return this.cpuUsage > this.idleThreshold / 100 ? 'active' : 'idle'
	}

	get frames() {
		return this.sprites[this.characterState]
	}

	get systemMonitorCommand() {
		const useCustomSystemMonitor = this.settings.get_boolean(SettingsSchemaKeys.CUSTOM_SYSTEM_MONITOR.ENABLED)
		const customSystemMonitorCommand = this.settings.get_string(SettingsSchemaKeys.CUSTOM_SYSTEM_MONITOR.COMMAND)

		return useCustomSystemMonitor ? customSystemMonitorCommand : SYSTEM_MONITOR_COMMAND
	}

	initDataRefreshSource() {
		const cpuDataProvider = createCpuGenerator()

		const refresh = () => {
			cpuDataProvider.next().then(({ value }) => { this.cpuUsage = value }, e => console.error(`${LOG_PREFIX}: ${e}`))

			return GLib.SOURCE_CONTINUE
		}

		this.refreshDataTimeoutId = GLib.timeout_add(GLib.PRIORITY_DEFAULT, 3_000, refresh)
		refresh()
	}

	initUi() {
		const box = new St.BoxLayout({
			styleClass: 'panel-status-menu-box gpucat-menu',
		})

		const icon = new St.Icon({
			styleClass: 'system-status-icon gpucat-menu__icon',
		})

		const label = new St.Label({
			text: '...',
			styleClass: 'gpucat-menu__label',
			xExpand: true,
			yExpand: true,
			xAlign: Clutter.ActorAlign.FILL,
			yAlign: Clutter.ActorAlign.CENTER,
		})

		this.bind_property_full(ReactiveProperties.CPU_USAGE, label, 'text', GObject.BindingFlags.SYNC_CREATE, (_, usage) => [true, formatNumber(usage)], null)
		this.bind_property_full(ReactiveProperties.DISPLAYING_ITEMS, label, 'visible', GObject.BindingFlags.SYNC_CREATE, (_, { percentage }) => [true, percentage], null)
		this.bind_property(ReactiveProperties.CURRENT_SPRITE_FRAME, icon, 'gicon', GObject.BindingFlags.DEFAULT)
		this.bind_property_full(ReactiveProperties.DISPLAYING_ITEMS, icon, 'visible', GObject.BindingFlags.SYNC_CREATE, (_, { character }) => [true, character], null)
		this.icon = icon
		this.applyColor()
		box.add_child(icon)
		box.add_child(label)
		this.add_child(box)
		this.initAnimation()
		this.menu.addAction(_('Open System Monitor'), () => {
			try {
				trySpawnCommandLine(this.systemMonitorCommand)
			}
			catch (e) {
				if (e instanceof Error) {
					Main.notifyError(_('Execution of “%s” failed').format(this.systemMonitorCommand), e.message)
				}

				console.error(e)
			}
		})

		this.menu.addMenuItem(new PopupSeparatorMenuItem())
		this.menu.addAction(_('Settings'), () => {
			try {
				this.extension.openPreferences()
			}
			catch (e) {
				if (e instanceof Error) {
					Main.notifyError(_('Failed to open extension settings'), e.message)
				}

				console.error(e)
			}
		})
	}

	initAnimation() {
		const ticker = createAnimationTicker()

		const showNextFrame = () => {
			const nowMs = GLib.get_monotonic_time() / 1_000
			const { index, nextDelayMs } = ticker.advanceTo(nowMs, this.frames.length)
			this.setCurrentSpriteFrame(this.frames[index])
			this.stopAnimation()
			this.animationTimeoutId = GLib.timeout_add(GLib.PRIORITY_DEFAULT, nextDelayMs, showNextFrame)

			return GLib.SOURCE_REMOVE
		}

		let lastState = null

		const updateAnimationState = (immediate = false) => {
			const utilization = this.isSpeedInverted
				? MAX_CPU_UTILIZATION - this.cpuUsage
				: this.cpuUsage

			// switching between running and sleeping jumps straight to the new pace
			const state = this.characterState
			const stateChanged = state !== lastState
			lastState = state

			const durationMs = state === 'idle'
				? IDLE_ANIMATION_CYCLE_DURATION_MS
				: getAnimationCycleDurationMs(utilization)
			ticker.setTargetDuration(durationMs, immediate || stateChanged)

			const shouldAnimate = this.displayingItems.character && this.frames.length > 1
			const shouldRestart = immediate || stateChanged || this.animationTimeoutId === null

			if (!shouldAnimate) {
				this.stopAnimation()
				this.setCurrentSpriteFrame(this.frames[0] ?? null)
			}
			else if (shouldRestart) {
				showNextFrame()
			}
		}

		for (const prop of [
			ReactiveProperties.CPU_USAGE,
			ReactiveProperties.IS_SPEED_INVERTED,
			ReactiveProperties.IDLE_THRESHOLD,
			ReactiveProperties.DISPLAYING_ITEMS,
			ReactiveProperties.IS_ANIMATION_SMOOTHING_ENABLED,
		]) {
			this.connect(`notify::${prop}`, () => updateAnimationState(!this.isAnimationSmoothingEnabled || prop === ReactiveProperties.IS_SPEED_INVERTED))
		}

		this.updateAnimationState = updateAnimationState
		updateAnimationState()
	}

	setCurrentSpriteFrame(sprite) {
		if (sprite !== this.currentSpriteFrame) {
			this.currentSpriteFrame = sprite
		}
	}

	stopAnimation() {
		if (this.animationTimeoutId !== null) {
			GLib.source_remove(this.animationTimeoutId)
			this.animationTimeoutId = null
		}
	}

	applyColor() {
		const color = resolveColor(this.settings.get_string(SettingsSchemaKeys.COLOR))
		this.icon?.set_style(`color: ${color};`)
	}

	initSettingsListeners() {
		this.settings.bind(SettingsSchemaKeys.INVERT_SPEED, this, ReactiveProperties.IS_SPEED_INVERTED, Gio.SettingsBindFlags.DEFAULT)
		this.settings.bind(SettingsSchemaKeys.IDLE_THRESHOLD, this, ReactiveProperties.IDLE_THRESHOLD, Gio.SettingsBindFlags.DEFAULT)
		this.settings.bind(SettingsSchemaKeys.SMOOTH_SPEED_CHANGES, this, ReactiveProperties.IS_ANIMATION_SMOOTHING_ENABLED, Gio.SettingsBindFlags.DEFAULT)
		const updateDisplayingItems = () => {
			const nick = this.settings.get_string(SettingsSchemaKeys.DISPLAYING_ITEMS)
			this.displayingItems = displayingItemNickToValue[nick]
		}

		this.displayingItemsHandlerId = this.settings.connect(`changed::${SettingsSchemaKeys.DISPLAYING_ITEMS}`, updateDisplayingItems)
		updateDisplayingItems()
		this.colorHandlerId = this.settings.connect(`changed::${SettingsSchemaKeys.COLOR}`, () => this.applyColor())
		this.characterHandlerId = this.settings.connect(`changed::${SettingsSchemaKeys.CHARACTER}`, () => {
			this.sprites = getSpritesPack(this.extension.path, this.settings.get_string(SettingsSchemaKeys.CHARACTER))
			this.updateAnimationState?.(true)
		})
	}

	destroy() {
		GLib.source_remove(this.refreshDataTimeoutId)
		this.settings.disconnect(this.displayingItemsHandlerId)
		this.settings.disconnect(this.colorHandlerId)
		this.settings.disconnect(this.characterHandlerId)
		this.stopAnimation()
		super.destroy()
	}
}
