// Optional macOS QA renderer, not a live terminal screenshot.
#import <AppKit/AppKit.h>

static NSColor *rgb(int r, int g, int b) {
    return [NSColor colorWithDeviceRed:r / 255.0 green:g / 255.0 blue:b / 255.0 alpha:1];
}

// Interpret only RGB SGR and reset emitted by presentation.py (not a terminal emulator).
static NSUInteger sgrLength(NSString *line, NSUInteger i, NSColor **foreground,
                            NSColor **background, NSColor *defaultBackground) {
    if (i + 1 >= line.length || [line characterAtIndex:i] != 27 || [line characterAtIndex:i + 1] != '[') return 0;
    NSRange end = [line rangeOfString:@"m" options:0 range:NSMakeRange(i + 2, line.length - i - 2)];
    if (end.location == NSNotFound) return 0;
    NSString *sequence = [line substringWithRange:NSMakeRange(i + 2, end.location - i - 2)];
    NSArray *parts = [sequence componentsSeparatedByString:@";"];
    if ([sequence isEqualToString:@"0"]) {
        *foreground = [NSColor whiteColor]; *background = defaultBackground;
    } else if (parts.count == 5 && [parts[1] intValue] == 2) {
        NSColor *color = rgb([parts[2] intValue], [parts[3] intValue], [parts[4] intValue]);
        if ([parts[0] intValue] == 38) *foreground = color;
        else if ([parts[0] intValue] == 48) *background = color;
        else return 0;
    } else return 0;
    return end.location - i + 1;
}

static int cellWidth(unichar c) {
    if ([[NSCharacterSet nonBaseCharacterSet] characterIsMember:c]) return 0;
    if ((c >= 0x1100 && c <= 0x115F) || (c >= 0x2E80 && c <= 0xA4CF)
        || (c >= 0xAC00 && c <= 0xD7A3) || (c >= 0xF900 && c <= 0xFAFF)
        || (c >= 0xFE10 && c <= 0xFE6F) || (c >= 0xFF01 && c <= 0xFF60)) return 2;
    return 1;
}

int main(int argc, const char *argv[]) {
    @autoreleasepool {
        if (argc < 2) { fprintf(stderr, "Usage: preview snapshot.txt ...\n"); return 1; }
        NSDictionary *attrs = @{NSFontAttributeName: [NSFont userFixedPitchFontOfSize:15],
                                NSForegroundColorAttributeName: [NSColor whiteColor]};
        // Fill two-cell Hangul glyphs without the exaggerated tracking of the Latin font fallback.
        NSDictionary *wideAttrs = @{NSFontAttributeName: [NSFont systemFontOfSize:19],
                                    NSForegroundColorAttributeName: [NSColor whiteColor]};
        for (int arg = 1; arg < argc; arg++) {
            NSString *path = [NSString stringWithUTF8String:argv[arg]];
            NSError *error = nil;
            NSString *text = [NSString stringWithContentsOfFile:path encoding:NSUTF8StringEncoding error:&error];
            if (!text) { fprintf(stderr, "%s\n", error.localizedDescription.UTF8String); return 1; }
            NSMutableArray *lines = [[text componentsSeparatedByString:@"\n"] mutableCopy];
            if ([[lines lastObject] isEqualToString:@""]) [lines removeLastObject];
            int columns = 0;
            for (NSString *line in lines) {
                int n = 0;
                NSColor *fg = [NSColor whiteColor], *bg = [NSColor blackColor];
                for (NSUInteger i = 0; i < line.length; i++) {
                    NSUInteger skip = sgrLength(line, i, &fg, &bg, [NSColor blackColor]);
                    if (skip) { i += skip - 1; continue; }
                    n += cellWidth([line characterAtIndex:i]);
                }
                columns = MAX(columns, n);
            }
            NSInteger width = columns * 10 + 40, height = lines.count * 23 + 40;
            NSBitmapImageRep *bitmap = [[NSBitmapImageRep alloc]
                initWithBitmapDataPlanes:NULL pixelsWide:width pixelsHigh:height
                bitsPerSample:8 samplesPerPixel:4 hasAlpha:YES isPlanar:NO
                colorSpaceName:NSDeviceRGBColorSpace bytesPerRow:0 bitsPerPixel:0];
            [NSGraphicsContext saveGraphicsState];
            [NSGraphicsContext setCurrentContext:[NSGraphicsContext graphicsContextWithBitmapImageRep:bitmap]];
            NSColor *defaultBackground = [path.pathExtension isEqualToString:@"ansi"] ? rgb(12, 18, 28) : [NSColor blackColor];
            [defaultBackground setFill];
            NSRectFill(NSMakeRect(0, 0, width, height));
            for (NSUInteger row = 0; row < lines.count; row++) {
                NSString *line = lines[row];
                int column = 0;
                NSColor *fg = [NSColor whiteColor], *bg = defaultBackground;
                NSMutableArray *glyphs = [NSMutableArray array];
                for (NSUInteger i = 0; i < line.length; i++) {
                    NSUInteger skip = sgrLength(line, i, &fg, &bg, defaultBackground);
                    if (skip) { i += skip - 1; continue; }
                    unichar c = [line characterAtIndex:i];
                    NSPoint point = NSMakePoint(20 + column * 10, height - 20 - (row + 1) * 23);
                    [bg setFill];
                    NSRectFill(NSMakeRect(point.x, point.y, cellWidth(c) * 10, 23));
                    NSMutableDictionary *style = [(cellWidth(c) == 2 ? wideAttrs : attrs) mutableCopy];
                    style[NSForegroundColorAttributeName] = fg;
                    NSFont *font = style[NSFontAttributeName];
                    NSPoint origin = NSMakePoint(point.x, point.y + 4 + font.descender);
                    [glyphs addObject:@{@"text": [NSString stringWithCharacters:&c length:1],
                                        @"point": [NSValue valueWithPoint:origin], @"style": style}];
                    column += cellWidth(c);
                }
                // Paint every background first; subsequent cells must not erase glyph edges.
                for (NSDictionary *glyph in glyphs) {
                    [glyph[@"text"] drawAtPoint:[glyph[@"point"] pointValue] withAttributes:glyph[@"style"]];
                }
            }
            [NSGraphicsContext restoreGraphicsState];
            NSString *target = [[path stringByDeletingPathExtension] stringByAppendingPathExtension:@"png"];
            NSData *data = [bitmap representationUsingType:NSBitmapImageFileTypePNG properties:@{}];
            if (![data writeToFile:target options:NSDataWritingAtomic error:&error]) {
                fprintf(stderr, "Could not write PNG\n"); return 1;
            }
            printf("%s\n", target.UTF8String);
        }
    }
    return 0;
}
