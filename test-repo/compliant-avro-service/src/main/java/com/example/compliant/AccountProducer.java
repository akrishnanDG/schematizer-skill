package com.example.compliant;

import io.confluent.kafka.serializers.KafkaAvroSerializer;
import org.apache.kafka.clients.producer.KafkaProducer;
import org.apache.kafka.clients.producer.ProducerRecord;
import org.apache.kafka.common.serialization.StringSerializer;

import java.util.Properties;

/**
 * Compliant Avro producer — Category A.
 * Uses KafkaAvroSerializer with Schema Registry, auto.register.schemas=false.
 */
public class AccountProducer {

    private final KafkaProducer<String, Object> producer;

    public AccountProducer(String bootstrapServers, String schemaRegistryUrl) {
        Properties props = new Properties();
        props.put("bootstrap.servers", bootstrapServers);
        props.put("key.serializer", StringSerializer.class.getName());
        props.put("value.serializer", KafkaAvroSerializer.class.getName());
        props.put("schema.registry.url", schemaRegistryUrl);
        props.put("auto.register.schemas", false);
        props.put("use.latest.version", true);
        this.producer = new KafkaProducer<>(props);
    }

    public void sendAccount(Object account) {
        producer.send(new ProducerRecord<>("account-events", account));
    }

    public void close() {
        producer.close();
    }
}
