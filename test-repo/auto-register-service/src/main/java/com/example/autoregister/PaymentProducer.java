package com.example.autoregister;

import io.confluent.kafka.serializers.KafkaAvroSerializer;
import org.apache.kafka.clients.producer.KafkaProducer;
import org.apache.kafka.clients.producer.ProducerRecord;
import org.apache.kafka.common.serialization.StringSerializer;

import java.util.Properties;

/**
 * Category C — uses Schema Registry but with auto.register.schemas=true.
 */
public class PaymentProducer {

    private final KafkaProducer<String, Object> producer;

    public PaymentProducer(String bootstrapServers, String schemaRegistryUrl) {
        Properties props = new Properties();
        props.put("bootstrap.servers", bootstrapServers);
        props.put("key.serializer", StringSerializer.class.getName());
        props.put("value.serializer", KafkaAvroSerializer.class.getName());
        props.put("schema.registry.url", schemaRegistryUrl);
        props.put("auto.register.schemas", true);
        props.put("use.latest.version", true);
        this.producer = new KafkaProducer<>(props);
    }

    public void sendPayment(Object payment) {
        producer.send(new ProducerRecord<>("payment-events", payment));
    }

    public void close() {
        producer.close();
    }
}
