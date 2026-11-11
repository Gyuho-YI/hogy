package com.hogy.cockpit.config;

import java.io.IOException;
import java.io.InputStream;
import java.util.Properties;

/** 빌드 시 주입된 앱 버전(cockpit-version.properties). Spring 기동 전(런처)에서도 사용. */
public final class AppVersion {

    private static final String VERSION = load();

    private AppVersion() {
    }

    public static String current() {
        return VERSION;
    }

    private static String load() {
        try (InputStream in = AppVersion.class.getResourceAsStream("/cockpit-version.properties")) {
            if (in == null) {
                return "dev";
            }
            Properties p = new Properties();
            p.load(in);
            String v = p.getProperty("version", "dev").trim();
            return v.isEmpty() || v.startsWith("@") ? "dev" : v;
        } catch (IOException e) {
            return "dev";
        }
    }
}
