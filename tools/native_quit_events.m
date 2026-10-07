// Native event source for verify_native_quit.py. It only addresses its own process.
#import <AppKit/AppKit.h>
#include <string.h>

static id eventMonitor;
static int commandQEvents;

int miwl_frontmost_pid(void) {
    return NSWorkspace.sharedWorkspace.frontmostApplication.processIdentifier;
}

int miwl_application_active(void) {
    return NSApp.active;
}

int miwl_command_q_events(void) {
    return commandQEvents;
}

static NSMenuItem *quitItem(NSMenu *menu) {
    for (NSMenuItem *item in menu.itemArray) {
        if ([item.keyEquivalent isEqualToString:@"q"]
                && (item.keyEquivalentModifierMask & NSEventModifierFlagCommand)) {
            return item;
        }
        NSMenuItem *nested = item.submenu ? quitItem(item.submenu) : nil;
        if (nested) return nested;
    }
    return nil;
}

const char *miwl_quit_menu_action(void) {
    static char action[256];
    NSMenuItem *item = quitItem(NSApp.mainMenu);
    if (!item || !item.enabled || !item.action) return "";
    strlcpy(action, NSStringFromSelector(item.action).UTF8String, sizeof(action));
    return action;
}

void miwl_observe_command_q(void) {
    eventMonitor = [NSEvent addLocalMonitorForEventsMatchingMask:NSEventMaskKeyDown
        handler:^NSEvent *(NSEvent *event) {
            if (event.keyCode == 12 && (event.modifierFlags & NSEventModifierFlagCommand)) {
                commandQEvents++;
            }
            return event;
        }];
}

int miwl_post_command_q(int count) {
    if (count < 1 || count > 3) return 0;
    NSWindow *window = NSApp.mainWindow;
    if (!window) {
        for (NSWindow *candidate in NSApp.windows) {
            if (candidate.visible) { window = candidate; break; }
        }
    }
    if (!window || !quitItem(NSApp.mainMenu)) return 0;
    for (int index = 0; index < count; index++) {
        for (int down = 1; down >= 0; down--) {
            NSEvent *event = [NSEvent keyEventWithType:
                    (down ? NSEventTypeKeyDown : NSEventTypeKeyUp)
                location:NSZeroPoint modifierFlags:NSEventModifierFlagCommand
                timestamp:NSProcessInfo.processInfo.systemUptime
                windowNumber:window.windowNumber context:nil
                characters:@"q" charactersIgnoringModifiers:@"q" isARepeat:NO keyCode:12];
            [NSApp postEvent:event atStart:NO];
        }
    }
    return count;
}
