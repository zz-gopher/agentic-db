package org.agentic;

import com.google.gson.Gson;
import org.apache.ibatis.builder.xml.XMLMapperBuilder;
import org.apache.ibatis.mapping.BoundSql;
import org.apache.ibatis.mapping.MappedStatement;
import org.apache.ibatis.session.Configuration;

import java.io.ByteArrayInputStream;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Paths;
import java.util.*;

public class Main {
    public static void main(String[] args) {
        if (args.length < 1) {
            System.err.println("Usage: java -jar agenticdb-parser.jar <path-to-mapper.xml>");
            System.exit(1);
        }

        String xmlPath = args[0];
        try {
            // 1. 以纯文本形式将 XML 完整读入内存
            String xmlContent = Files.readString(Paths.get(xmlPath));

            // 2. 内存级“降维拦截”（这是通用扫描器的核心魔法）
            // 无论用户的 resultType、parameterType 还是 resultMap 里的 type 写了什么自定义类，
            // 统一在内存流中强行洗成 "map"，彻底切断它与外部业务代码的反射依赖。
            xmlContent = xmlContent.replaceAll("\\b(resultType|parameterType|type)\\s*=\\s*[\"'][^\"']+[\"']", "$1=\"map\"");

            // 3. 将洗干净的字符串转回 InputStream，喂给 MyBatis 原生引擎
            ByteArrayInputStream inputStream = new ByteArrayInputStream(xmlContent.getBytes(StandardCharsets.UTF_8));

            Configuration configuration = new Configuration();
            XMLMapperBuilder builder = new XMLMapperBuilder(
                    inputStream, configuration, xmlPath, configuration.getSqlFragments()
            );
            builder.parse();

            Map<String, Object> mockParams = new HashMap<>() {
                @Override
                public Object get(Object key) {
                    String k = key.toString().toLowerCase();
                    if (k.contains("list") || k.contains("ids") || k.contains("array")) {
                        return Arrays.asList("mock_1", "mock_2");
                    }
                    return "1";
                }

                @Override
                public boolean containsKey(Object key) {
                    return true;
                }
            };

            List<Map<String, String>> results = new ArrayList<>();
            Set<String> processedIds = new HashSet<>();

            for (MappedStatement ms : configuration.getMappedStatements()) {
                String id = ms.getId();
                if (processedIds.contains(id)) continue;
                processedIds.add(id);

                try {
                    BoundSql boundSql = ms.getBoundSql(mockParams);
                    String sql = boundSql.getSql().replaceAll("\\s+", " ").trim();

                    Map<String, String> sqlData = new HashMap<>();
                    sqlData.put("id", id);
                    sqlData.put("sql", sql);
                    results.add(sqlData);
                } catch (Exception e) {
                    // 忽略缺乏严格上下文的 Fragment
                }
            }

            Gson gson = new Gson();
            System.out.println(gson.toJson(results));

        } catch (Exception e) {
            System.err.println("Error parsing XML: " + e.getMessage());
            System.exit(1);
        }
    }
}