package com.example.analytics;

import org.apache.kafka.clients.producer.KafkaProducer;
import org.apache.kafka.clients.producer.ProducerRecord;
import org.apache.kafka.common.serialization.StringSerializer;

import java.util.Properties;

public class ClickProducer {

    private final KafkaProducer<String, ClickEvent> producer;

    public ClickProducer(String bootstrapServers) {
        Properties props = new Properties();
        props.put("bootstrap.servers", bootstrapServers);
        props.put("key.serializer", StringSerializer.class.getName());
        props.put("value.serializer", ClickEventSerializer.class.getName());
        this.producer = new KafkaProducer<>(props);
    }

    public void sendClick(ClickEvent event) {
        producer.send(new ProducerRecord<>("click-events", event.getSessionId(), event));
    }

    public void close() {
        producer.close();
    }
}
